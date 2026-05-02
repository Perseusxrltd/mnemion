#!/usr/bin/env python3
"""
backfill_trust.py — Assign default trust records to all existing drawers.
Run once after deploying the trust layer.

Usage:  py ~/.mnemion/backfill_trust.py
"""

import importlib
import os
import sys


def _ensure_source_on_path() -> None:
    source_dir = os.environ.get("MNEMION_SOURCE_DIR", os.path.expanduser("~/projects/mnemion"))
    if os.path.isdir(source_dir) and source_dir not in sys.path:
        sys.path.insert(0, source_dir)


def main() -> None:
    _ensure_source_on_path()

    chromadb = importlib.import_module("chromadb")
    MnemionConfig = importlib.import_module("mnemion.config").MnemionConfig
    DrawerTrust = importlib.import_module("mnemion.trust_lifecycle").DrawerTrust

    config = MnemionConfig()
    client = chromadb.PersistentClient(path=config.anaktoron_path)

    try:
        col = client.get_collection(config.collection_name)
    except Exception as e:
        print(f"Failed to open collection: {e}")
        sys.exit(1)

    print(f"Anaktoron: {config.anaktoron_path}")
    total = col.count()
    print(f"Total drawers: {total}")

    trust = DrawerTrust()

    batch_size = 500
    offset = 0
    inserted = 0

    while offset < total:
        batch = col.get(
            include=["metadatas"],
            limit=batch_size,
            offset=offset,
        )
        ids = batch["ids"]
        metas = batch["metadatas"]

        tuples = [
            (did, (m or {}).get("wing", "unknown"), (m or {}).get("room", "unknown"))
            for did, m in zip(ids, metas)
        ]
        n = trust.bulk_create_default(tuples)
        inserted += n
        offset += len(ids)
        print(f"  {offset}/{total} processed, {inserted} new trust records")

    print(f"\nDone. {inserted} trust records created (existing ones skipped).")
    stats = trust.stats()
    print(f"Trust stats: {stats}")


if __name__ == "__main__":
    main()
