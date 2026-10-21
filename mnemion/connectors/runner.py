"""Portable connector runner. Only complete inventories authorize pruning."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import ValidationError

from ..local_state import LocalSetupError
from ..sdk import Client, MnemionError
from ..version import __version__
from .capture_cycle import BACKFILL_POLL_SECONDS, backfill_pending
from .config import read_config
from .conversation_inbox import InboxError
from .protocol import ConnectorClient, SkippedDocument
from .live_conversations import ConversationProvider
from .journal_projection import project_documents
from .provenance import git_commit
from .providers import FilesystemProvider, GitProvider, ProviderError, RcloneProvider

MANAGED_PROTOCOL = 1
HEADLESS_CAPTURE_PROTOCOL = 1
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
            "Use access_mode published for filesystem, conversations, git and rclone; "
            "use access_mode provider for slack and gdrive."
        ),
        "conversation_server_upgrade_required": (
            "Live conversation capture requires Mnemion server 4.17.0 or later."
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
        "conversations": ConversationProvider,
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
        if isinstance(adapter, ConversationProvider) and not inspect:
            value = client.request("GET", "/health/live").get("service_version", "")
            try:
                supported = len(value.split(".")) == 3 and tuple(map(int, value.split("."))) >= (
                    4,
                    17,
                    0,
                )
            except (TypeError, ValueError, AttributeError):
                supported = False
            if not supported:
                raise ConnectorConfigurationError("conversation_server_upgrade_required")
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

                context = (
                    adapter.snapshot(identifier, target.get("checkpoint"))
                    if isinstance(adapter, ConversationProvider)
                    else nullcontext(None)
                )
                with context as snapshot:
                    skipped = {"skipped_documents": 0, "file_errors": []}

                    def items():
                        if snapshot is not None:
                            yield from snapshot.items()
                        else:
                            for value in project_documents(adapter.documents(identifier)):
                                if value is None:
                                    yield None
                                elif isinstance(value, SkippedDocument):
                                    if (
                                        not skipped["skipped_documents"]
                                        and client.request("GET", "/health/live").get(
                                            "connector_partial_inventory"
                                        )
                                        is not True
                                    ):
                                        raise ProviderError("text_source_server_upgrade_required")
                                    skipped["skipped_documents"] += 1
                                    if len(skipped["file_errors"]) < 50:
                                        skipped["file_errors"].append(value.report())
                                    yield None
                                else:
                                    yield from value.items()
                        # Validate effective access again before a deletion sweep.
                        bridge.refresh(
                            adapter.access(identifier), lease_seconds=config.access_lease_seconds
                        )
                        if snapshot is not None:
                            yield None  # Publish the final verified capture counters.

                    try:
                        result = bridge.sync(
                            target["space_id"],
                            items(),
                            checkpoint=(lambda: snapshot.checkpoint) if snapshot else checkpoint,
                            heartbeat=heartbeat,
                            inventory_errors=lambda: (
                                skipped if skipped["skipped_documents"] else {}
                            ),
                        )
                    except MnemionError as exc:
                        if snapshot and exc.code == "source_reference_unavailable":
                            snapshot.invalidate()
                        raise
                    if snapshot is not None:
                        snapshot.acknowledge()
                        result["capture"] = snapshot.report
                    if result.get("incomplete_inventory"):
                        report["completed"] = False
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
        changed=report.get("changed", 0)
        if "capture" in report
        else outcomes.get("created", 0) + outcomes.get("revised", 0),
        removed=report.get("removed", 0)
        if "capture" in report
        else removed + outcomes.get("deleted", 0),
        unchanged=report.get("unchanged", 0)
        if "capture" in report
        else outcomes.get("unchanged", 0),
        conflicts=report.get("conflicts", 0)
        if "capture" in report
        else outcomes.get("conflict", 0),
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
            "capture_backfill": backfill_pending(report),
            "scanned_commit": git_commit("git:" + str(report.get("scanned_commit", ""))),
            "scanned_at": report["timestamp"],
        },
    )


def sync(config, *, inspect=False, adapter=None, client=None) -> dict:
    started, started_at = time.monotonic(), datetime.now(timezone.utc).isoformat()
    if config.capture is not None:
        from . import headless_capture

        if adapter is not None:
            raise ValueError("Retained capture owns its selected conversation adapter")
        if inspect:
            return {
                "completed": True,
                "connector_id": str(config.connector_id),
                "preview": headless_capture.preview(config),
            }
        # The entire local cycle must precede credential reads, HTTP setup and
        # remote scheduling. Offline intake is not conditional on control health.
        report = headless_capture.scan(
            config, client_factory=(lambda: nullcontext(client)) if client else None
        )
        _stamp(report, started_at, started)
        if not report.get("paused") and config.remote_sync:
            try:
                with nullcontext(client) if client else headless_capture.connect(config) as remote:
                    control = control_status(remote, config.connector_id)
                    _report_control(remote, config.connector_id, control, report)
            except (
                MnemionError,
                OSError,
                ValueError,
                httpx.HTTPError,
                headless_capture.InboxError,
            ):
                report["control_reported"] = False
        return report
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


def wait_for_sync(config, *, failed=False, backfill=False, client=None, clock=None, sleep=None):
    """Poll only a small control record; never fetch the source between scans."""
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    interval = (
        min(config.poll_seconds, BACKFILL_POLL_SECONDS)
        if config.capture is not None and backfill
        else config.poll_seconds
    )
    deadline = clock() + interval
    retry_at = clock() + (min(30, config.poll_seconds) if failed else 0)
    was_paused = False

    def capture_active():
        from .headless_capture import read_record

        try:
            record = read_record(config)
            return record["enabled"] and record["state"] == "ready"
        except (InboxError, LocalSetupError, OSError, ValueError):
            return False

    if config.capture is not None:
        was_paused = not capture_active()
    while clock() < deadline:
        sleep(min(config.trigger_poll_seconds, max(0, deadline - clock())))
        if clock() >= deadline:
            break
        if config.capture is not None:
            active = capture_active()
            if was_paused and active:
                return "requested"
            was_paused = not active
            if not active:
                continue
        if not config.remote_sync or clock() < retry_at:
            continue
        owned_client = client is None
        current = None
        try:
            if client is None:
                if config.capture is not None:
                    from .headless_capture import reference

                    credential = reference(config.service_token)
                else:
                    credential = config.service_token.read()
                current = Client(config.service_url, credential, timeout=10, retries=0)
            else:
                current = client
            control = control_status(current, config.connector_id)
            if control is None:
                sleep(max(0, deadline - clock()))
                break
            if control["pending"]:
                return "requested"
        except (MnemionError, OSError, ValueError, httpx.HTTPError, InboxError):
            # Back off control failures without suppressing the normal source scan.
            retry_at = clock() + 30
        finally:
            if owned_client and current is not None:
                current.close()
    return "poll"


def main(argv=None) -> int:
    from .runner_options import arguments

    parser = argparse.ArgumentParser(
        description="Connect company sources to a scoped Mnemion memory service"
    )
    arguments(parser)
    return execute(parser.parse_args(argv), parser)


def execute(args, parser) -> int:
    """Run the same connector contract from either installed entry point."""
    if args.capture_control and (args.watch or args.inspect or args.managed_state):
        parser.error("--capture-control cannot be combined with another mode")
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
        backfill = False
        try:
            config = read_config(args.config)
            if args.capture_control:
                from .capture_resources import bounded
                from .headless_capture_control import perform

                body = sys.stdin.buffer.read(65537)
                if len(body) > 65536:
                    raise ValueError("Capture control input exceeds its limit")
                if config.capture is None:
                    raise InboxError("capture_enrollment_missing")
                with bounded(config.capture.memory_limit_mib):
                    result = perform(config, json.loads(body))
                print(json.dumps({"ok": True, "result": result}, ensure_ascii=False), flush=True)
                return 0
            if config.capture is not None:
                from .capture_resources import bounded

                with bounded(config.capture.memory_limit_mib):
                    report = sync(config, inspect=args.inspect)
            else:
                report = sync(config, inspect=args.inspect)
            report["trigger"] = trigger
            report["poll_seconds"] = config.poll_seconds
            if not args.inspect:
                _report_managed(report)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            backfill = config.capture is not None and backfill_pending(report)
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
        except (
            ProviderError,
            MnemionError,
            ValueError,
            OSError,
            httpx.HTTPError,
            InboxError,
            LocalSetupError,
        ) as exc:
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
                trigger = wait_for_sync(config, failed=code != 0, backfill=backfill)
            else:
                time.sleep(300)
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
