"""Build a host-format fixture from the installed gate's real encrypted snapshot.

This is test data preparation, never a production conversion or host adoption.
The desktop still authenticates, inspects and restores the resulting file.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
import zipfile

from mnemion import backup_encryption as encryption, local_state as state
from mnemion.archives import MANIFEST, private_json, write_archive
from mnemion.service import host_package, recovery


def create(source: Path, key: str, output: Path, *, embedded_ledger: Path | None = None) -> dict:
    with state.temporary_directory(prefix="native-host-fixture-", dir=output.parent) as scratch:
        database, ledger = scratch / "database.mnemion", scratch / "ledger.json"
        encryption.decrypt_file(source, database, key, expected_kind="snapshot")
        with zipfile.ZipFile(database) as archive:
            manifest = json.loads(archive.read(MANIFEST))
            if embedded_ledger is None:
                with archive.open("deletions.json") as original, ledger.open("xb") as target:
                    while block := original.read(1024 * 1024):
                        target.write(block)
        if embedded_ledger is not None:
            with embedded_ledger.open("rb") as original, ledger.open("xb") as target:
                while block := original.read(1024 * 1024):
                    target.write(block)
        current = recovery.read_ledger(ledger)
        package_id = str(uuid4())
        plan = {
            "format": host_package.FORMAT,
            "version": 1,
            "package_id": package_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "service_version": manifest["application_version"],
            "backup_id": manifest["backup_id"],
            "snapshot_at": manifest["snapshot_at"],
            "ledger_at": current["snapshot_at"],
            "postgres_major": manifest["server_version"] // 10000,
            "tenant_ids": manifest["tenant_ids"],
            "counts": {
                name: item["count"]
                for name, item in manifest["tables"].items()
                if name in host_package.COUNTED_TABLES
            },
            "files": 1,
            "connectors": [],
            "source_updates": {"mode": "managed", "enabled": True},
            "public_origin_configured": True,
            "network_listener": False,
            "application_keys_in_ledger": 0,
            "external_transport_verified": False,
            "model_cache_included": False,
        }
        host, asset = scratch / "host.json", scratch / "asset-000"
        private_json(asset, {"synthetic_secret": "private-host-import-fixture-sentinel"})
        private_json(
            host,
            {
                "plan": plan,
                "host": "127.0.0.1",
                "port": 7890,
                "public_url": "https://old-host.invalid",
                "environment": {"MNEMION_FIXTURE_CONFIG": "/old-host/private-provider.json"},
                "assets": [
                    {"id": "asset-000", "source": "/old-host/private-provider.json", "json": True}
                ],
                "connectors": [],
            },
        )
        archive = scratch / "host.mnemion"
        write_archive(
            archive,
            {
                "database.mnemion": database,
                "ledger.json": ledger,
                "host.json": host,
                "assets/asset-000": asset,
            },
            {"format": host_package.FORMAT, "version": 1, "package_id": package_id},
        )
        encrypted = encryption.encrypt_file(archive, output, key, kind="bundle")
        return {
            "file": str(output),
            "sha256": encrypted.encrypted_sha256,
            "package_id": package_id,
            "source": "native-gate-host-format-fixture",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = state.read(args.fixture)
    if "host" in fixture:
        raise ValueError("The host fixture is already prepared")
    fixture["host"] = create(Path(fixture["snapshot"]["file"]), fixture["key"], args.output)
    state.write(args.fixture, fixture)
    print(json.dumps({"host_fixture_created": True, "production_host_adoption": False}))


if __name__ == "__main__":
    main()
