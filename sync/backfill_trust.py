#!/usr/bin/env python3
"""
backfill_trust.py — Assign default trust records to all existing drawers.
Run once after deploying the trust layer.

Usage:  py C:/Users/jorqu/.mnemion/backfill_trust.py
"""

import sys
import os

sys.path.insert(0, os.path.expanduser("~/projects/mnemion"))

from mnemion.chroma_compat import make_persistent_client  # noqa: E402
from mnemion.config import MnemionConfig  # noqa: E402
from mnemion.trust_lifecycle import DrawerTrust  # noqa: E402

config = MnemionConfig()
client = make_persistent_client(
    config.anaktoron_path, vector_safe=True, collection_name=config.collection_name
)

try:
    col = client.get_collection(config.collection_name)
except Exception as e:
    print(f"Failed to open collection: {e}")
    sys.exit(1)

print(f"Anaktoron: {config.anaktoron_path}")
total = col.count()
print(f"Total drawers: {total}")

trust = DrawerTrust()

BATCH_SIZE = 500
offset = 0
inserted = 0

while offset < total:
    batch = col.get(
        include=["metadatas"],
        limit=BATCH_SIZE,
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
