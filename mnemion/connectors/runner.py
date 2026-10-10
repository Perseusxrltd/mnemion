"""Portable connector runner. Only complete inventories authorize pruning."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from pydantic import ValidationError

from ..sdk import Client, MnemionError
from .config import read_config
from .protocol import ConnectorClient
from .providers import FilesystemProvider, GitProvider, ProviderError, RcloneProvider


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


def sync(config, *, inspect=False, adapter=None, client=None) -> dict:
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
        if (
            not connection
            or connection["disabled_at"]
            or connection["provider"] != config.provider.type
        ):
            raise ValueError("The credential does not own an active connector for this provider")
        if connection["access_mode"] != adapter.access_mode:
            raise ValueError("The connector access mode does not match this source adapter")
        previous = {scope["external_id"]: scope for scope in bridge.scopes()}
        # Do not reconcile disappeared scopes unless the complete catalog loaded.
        identifiers = list(adapter.scopes())
        if len(set(identifiers)) != len(identifiers):
            raise ProviderError("ambiguous_scope_inventory")
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

                result = bridge.sync(target["space_id"], items(), heartbeat=heartbeat)
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Connect company sources to a scoped Mnemion memory service"
    )
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
    args = parser.parse_args(argv)
    if args.inspect and args.watch:
        parser.error("--inspect cannot be combined with --watch")
    while True:
        try:
            config = read_config(args.config)
            report = sync(config, inspect=args.inspect)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            code = 0 if report["completed"] else 2
        except ValidationError as exc:
            # Pydantic repr may include submitted token-shaped values. Report
            # locations only, never raw configuration or provider diagnostics.
            print(
                json.dumps(
                    {
                        "error": "invalid_config",
                        "fields": [".".join(map(str, error["loc"])) for error in exc.errors()],
                    }
                ),
                file=sys.stderr,
            )
            return 2
        except (ProviderError, MnemionError, ValueError, OSError, httpx.HTTPError) as exc:
            print(json.dumps({"error": getattr(exc, "code", "connector_failed")}), file=sys.stderr)
            code = 2
        if not args.watch:
            return code
        time.sleep(config.poll_seconds if "config" in locals() else 300)


if __name__ == "__main__":
    raise SystemExit(main())
