"""Portable connector runner. Only complete inventories authorize pruning."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import ValidationError

from ..sdk import Client, MnemionError
from ..version import __version__
from .config import read_config
from .protocol import ConnectorClient
from .provenance import git_commit
from .providers import FilesystemProvider, GitProvider, ProviderError, RcloneProvider

MANAGED_PROTOCOL = 1
SCAN_TRIGGER_ENV = "MNEMION_CONNECTOR_SCAN_TRIGGER"
SCAN_REPORT_ENV = "MNEMION_CONNECTOR_REPORT_PATH"


class ConnectorConfigurationError(ValueError):
    """Only these fixed operator hints may enter a scan failure report."""

    MESSAGES = {
        "connector_identity_unavailable": (
            "Use the active connector's dedicated application key and connector_id."
        ),
        "connector_provider_mismatch": (
            "The registered connector provider differs from provider.type in this config. "
            "Register the source adapter name; published and provider are access_mode values."
        ),
        "connector_access_mode_mismatch": (
            "Use access_mode published for filesystem, git and rclone; "
            "use access_mode provider for slack and gdrive."
        ),
    }

    def __init__(self, code):
        self.code = code
        super().__init__(self.MESSAGES[code])


def scan_trigger() -> str:
    # Managed one-shot scans inherit their watcher's reason. Older runtimes
    # simply ignore this optional environment value, preserving rollback.
    value = os.environ.get(SCAN_TRIGGER_ENV, "startup")
    return value if value in {"startup", "poll", "requested"} else "startup"


def provider(config):
    from .gdrive import DriveProvider
    from .slack import SlackProvider

    return {
        "filesystem": FilesystemProvider,
        "git": GitProvider,
        "rclone": RcloneProvider,
        "slack": SlackProvider,
        "gdrive": DriveProvider,
    }[config.type](config)


def _scan(config, *, inspect=False, adapter=None, client=None) -> dict:
    adapter = adapter or provider(config.provider)
    owned_client = client is None
    client = client or Client(config.service_url, config.service_token.read())
    bridge = ConnectorClient(client, config.connector_id)
    report = {
        "connector_id": str(config.connector_id),
        "provider": config.provider.type,
        "scopes": [],
        "completed": True,
    }
    try:
        connection = next(
            (
                value
                for value in client.request("GET", "/v1/connectors")["items"]
                if value["id"] == str(config.connector_id)
            ),
            None,
        )
        if not connection or connection["disabled_at"]:
            raise ConnectorConfigurationError("connector_identity_unavailable")
        if connection["provider"] != config.provider.type:
            raise ConnectorConfigurationError("connector_provider_mismatch")
        if connection["access_mode"] != adapter.access_mode:
            raise ConnectorConfigurationError("connector_access_mode_mismatch")
        previous = {scope["external_id"]: scope for scope in bridge.scopes()}
        # Do not reconcile disappeared scopes unless the complete catalog loaded.
        identifiers = list(adapter.scopes())
        if len(set(identifiers)) != len(identifiers):
            raise ProviderError("ambiguous_scope_inventory")
        # Pin the scan's repository snapshot independently of each file's last
        # change. The service commits this cursor only after complete inventory.
        checkpoint = f"git:{adapter.commit}" if isinstance(adapter, GitProvider) else None
        for identifier in identifiers:
            target = previous.get(identifier)
            try:
                access = adapter.access(identifier)
                if inspect:
                    report["scopes"].append(
                        {"external_id": identifier, "name": access.name, "members": access.members}
                    )
                    continue
                target = bridge.refresh(access, lease_seconds=config.access_lease_seconds)
                last_access = time.monotonic()

                def heartbeat():
                    nonlocal last_access
                    if time.monotonic() - last_access >= min(300, config.access_lease_seconds / 2):
                        bridge.refresh(
                            adapter.access(identifier), lease_seconds=config.access_lease_seconds
                        )
                        last_access = time.monotonic()

                def items():
                    for value in adapter.documents(identifier):
                        if value is None:
                            yield None
                        else:
                            yield from value.items()
                    # Validate effective access again before a deletion sweep.
                    bridge.refresh(
                        adapter.access(identifier), lease_seconds=config.access_lease_seconds
                    )

                result = bridge.sync(
                    target["space_id"], items(), checkpoint=checkpoint, heartbeat=heartbeat
                )
                report["scopes"].append({"external_id": identifier, **result})
            except (ProviderError, OSError, ValueError, MnemionError, httpx.HTTPError) as exc:
                report["completed"] = False
                code = getattr(exc, "code", "source_read_failed")
                entry = {"external_id": identifier, "error_code": code}
                # A competing connector run or a service transport failure must
                # not suspend another agent's valid ingestion lease.
                if target and not inspect and isinstance(exc, (ProviderError, OSError, ValueError)):
                    try:
                        bridge.suspend(
                            target["space_id"],
                            "access_lost"
                            if getattr(exc, "access_lost", False)
                            else "provider_unavailable",
                        )
                        entry["access_suspended"] = True
                    except (MnemionError, OSError, httpx.HTTPError):
                        entry["access_suspended"] = False
                report["scopes"].append(entry)
        if not inspect:
            for missing in previous.keys() - set(identifiers):
                bridge.suspend(previous[missing]["space_id"], "access_lost")
                report["scopes"].append(
                    {
                        "external_id": missing,
                        "access_suspended": True,
                        "reason": "not_in_current_catalog",
                    }
                )
        if not inspect and report["completed"] and git_commit(checkpoint):
            report["scanned_commit"] = git_commit(checkpoint)
        return report
    except ProviderError:
        # A catalog/authentication failure denies known scopes immediately when
        # the service is reachable. The stored ACL lease is the outage fallback.
        if not inspect:
            for scope in bridge.scopes():
                try:
                    bridge.suspend(scope["space_id"], "provider_unavailable")
                except (MnemionError, OSError, httpx.HTTPError):
                    pass
        raise
    finally:
        if hasattr(adapter, "close"):
            adapter.close()
        if owned_client:
            client.close()


def control_status(client, connector):
    """Old services retain ordinary polling until they are upgraded."""
    try:
        from ..service.connector_contracts import SyncStatus

        return SyncStatus.model_validate(
            client.request("GET", f"/v1/connectors/{connector}/sync")
        ).model_dump()
    except MnemionError as exc:
        if exc.status in {404, 405}:
            return None
        raise
    except ValidationError:
        raise MnemionError(
            502, "invalid_sync_status", "The service returned an invalid sync status."
        ) from None


def _stamp(report, started_at, started):
    outcomes = {}
    removed = 0
    for scope in report.get("scopes", []):
        removed += scope.get("removed", 0)
        for key, count in scope.get("outcomes", {}).items():
            outcomes[key] = outcomes.get(key, 0) + count
    report.update(
        event="connector_scan",
        runner_version=__version__,
        started_at=started_at,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_seconds=round(time.monotonic() - started, 3),
        changed=outcomes.get("created", 0) + outcomes.get("revised", 0),
        removed=removed + outcomes.get("deleted", 0),
        unchanged=outcomes.get("unchanged", 0),
        conflicts=outcomes.get("conflict", 0),
    )


def _report_control(client, connector, control, report):
    report["remote_sync_available"] = control is not None
    if control is None:
        return
    report["sync_generation"] = control["requested_generation"]
    body = {
        "generation": control["requested_generation"],
        "successful": report["completed"],
        "duration_seconds": min(604800, report["duration_seconds"]),
        "changed": report["changed"],
        "removed": report["removed"],
        "unchanged": report["unchanged"],
        "error_code": None if report["completed"] else "incomplete_inventory",
    }
    try:
        # A report is not replayed after an uncertain write. The durable pending
        # generation causes a safe subsequent scan if the acknowledgement was lost.
        client.request("POST", f"/v1/connectors/{connector}/sync/report", body=body)
        report["control_reported"] = True
    except (MnemionError, OSError, ValueError, httpx.HTTPError):
        report["control_reported"] = False


def _report_managed(report):
    """Optional private receipt; old rollback runtimes safely ignore the env."""
    destination = os.environ.get(SCAN_REPORT_ENV)
    if not destination or os.name != "posix":
        return
    from ..service import update_state

    update_state.write(
        Path(destination),
        {
            "format": 1,
            "connector_id": report["connector_id"],
            "runner_version": __version__,
            "completed": report["completed"],
            "scanned_commit": git_commit("git:" + str(report.get("scanned_commit", ""))),
            "scanned_at": report["timestamp"],
        },
    )


def sync(config, *, inspect=False, adapter=None, client=None) -> dict:
    started, started_at = time.monotonic(), datetime.now(timezone.utc).isoformat()
    owned_client = client is None
    client = client or Client(config.service_url, config.service_token.read())
    control = None
    try:
        if not inspect and config.remote_sync:
            control = control_status(client, config.connector_id)
        try:
            report = _scan(config, inspect=inspect, adapter=adapter, client=client)
        except (ProviderError, MnemionError, OSError, ValueError, httpx.HTTPError):
            report = {"completed": False, "scopes": []}
            _stamp(report, started_at, started)
            _report_control(client, config.connector_id, control, report)
            raise
        _stamp(report, started_at, started)
        if not inspect:
            _report_control(client, config.connector_id, control, report)
        return report
    finally:
        if owned_client:
            client.close()


def wait_for_sync(config, *, failed=False, client=None, clock=None, sleep=None):
    """Poll only a small control record; never fetch the source between scans."""
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    deadline = clock() + config.poll_seconds
    retry_at = clock() + (min(30, config.poll_seconds) if failed else 0)
    while clock() < deadline:
        sleep(min(config.trigger_poll_seconds, max(0, deadline - clock())))
        if clock() >= deadline:
            break
        if not config.remote_sync or clock() < retry_at:
            continue
        owned_client = client is None
        current = None
        try:
            current = client or Client(
                config.service_url, config.service_token.read(), timeout=10, retries=0
            )
            control = control_status(current, config.connector_id)
            if control is None:
                sleep(max(0, deadline - clock()))
                break
            if control["pending"]:
                return "requested"
        except (MnemionError, OSError, ValueError, httpx.HTTPError):
            # Back off control failures without suppressing the normal source scan.
            retry_at = clock() + 30
        finally:
            if owned_client and current is not None:
                current.close()
    return "poll"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Connect company sources to a scoped Mnemion memory service"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Read provider scope IDs and membership without importing or changing service access",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Repeat complete scans; configuration and token files reload between runs",
    )
    parser.add_argument(
        "--managed-state",
        type=Path,
        help="Use this local managed Linux/macOS service's verified runtime for each scan",
    )
    args = parser.parse_args(argv)
    if args.inspect and args.watch:
        parser.error("--inspect cannot be combined with --watch")
    if args.managed_state is not None:
        if not args.watch:
            parser.error("--managed-state requires --watch")
        from .managed import main as managed

        return managed(args.managed_state, args.config)
    if args.watch:
        print(
            json.dumps(
                {
                    "event": "connector_runtime",
                    "runner_version": __version__,
                    "update_mode": "manual",
                    "managed_mode": "Use --managed-state on an adopted local Linux/macOS host to follow verified updates",
                }
            ),
            flush=True,
        )
    trigger = "startup" if args.watch or args.inspect else scan_trigger()
    while True:
        started, started_at = time.monotonic(), datetime.now(timezone.utc).isoformat()
        try:
            config = read_config(args.config)
            report = sync(config, inspect=args.inspect)
            report["trigger"] = trigger
            report["poll_seconds"] = config.poll_seconds
            if not args.inspect:
                _report_managed(report)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            code = 0 if report["completed"] and report.get("control_reported") is not False else 2
        except ValidationError as exc:
            # Pydantic repr may include submitted token-shaped values. Report
            # locations only, never raw configuration or provider diagnostics.
            credential_fields = sorted(
                {
                    "service_token" if error["loc"][0] == "service_token" else "provider.token"
                    for error in exc.errors()
                    if error["loc"]
                    and (
                        error["loc"][0] == "service_token"
                        or error["loc"][0] == "provider"
                        and "token" in error["loc"]
                    )
                }
            )
            print(
                json.dumps(
                    {
                        "error": "invalid_config",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "fields": [".".join(map(str, error["loc"])) for error in exc.errors()],
                        "hints": [
                            {
                                "field": field,
                                "message": 'Use a {"file": "/path/to/private-token"} or {"env": "VARIABLE_NAME"} reference, not a token string.',
                            }
                            for field in credential_fields
                        ],
                    }
                ),
                file=sys.stderr,
            )
            return 2
        except (ProviderError, MnemionError, ValueError, OSError, httpx.HTTPError) as exc:
            print(
                json.dumps(
                    {
                        "event": "connector_scan_failed",
                        "runner_version": __version__,
                        "error": getattr(exc, "code", "connector_failed"),
                        **(
                            {"message": str(exc)}
                            if isinstance(exc, ConnectorConfigurationError)
                            else {}
                        ),
                        "started_at": started_at,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "duration_seconds": round(time.monotonic() - started, 3),
                        "trigger": trigger,
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
            code = 2
        if not args.watch:
            return code
        try:
            if "config" in locals():
                trigger = wait_for_sync(config, failed=code != 0)
            else:
                time.sleep(300)
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
