#!/usr/bin/env python3
"""
merge_exports.py — Safe merge of two drawers_export.json files.

Strategy
--------
- Union both drawer sets, deduplicated by drawer ID.
- When the same ID appears in both: keep the one with the newer ``filed_at``
  metadata timestamp; fall back to preferring --theirs on a tie or missing ts.
- Deletions are NOT propagated in this version (v1 limitation: a drawer
  deleted on one agent is resurrected after the next merge from another agent
  that still has it).  Tombstone propagation is tracked as a future feature.

Usage
-----
    python merge_exports.py --ours local.json --theirs remote.json --out merged.json

Exit codes
----------
    0  success
    1  error (file not found, invalid JSON, etc.)
"""

import argparse
import json
import sys
from datetime import datetime, timezone


def _parse_ts(meta: dict) -> datetime | None:
    """Parse filed_at / updated_at from a drawer metadata dict."""
    for key in ("filed_at", "updated_at", "created_at"):
        val = (meta or {}).get(key)
        if val:
            try:
                # Handle both "2026-04-13T10:00:00" and "2026-04-13T10:00:00Z"
                ts = datetime.fromisoformat(val.replace("Z", "+00:00"))
                # Normalise to UTC-aware for comparison
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return ts
            except (ValueError, AttributeError):
                continue
    return None


def _load(path: str) -> dict:
    """Load a drawers_export.json; returns {drawer_id: drawer_dict}."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        # Treat missing file as an empty export (first sync)
        return {}
    except json.JSONDecodeError as exc:
        print(f"ERROR: {path} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        print(f"ERROR: {path} must be a JSON array", file=sys.stderr)
        sys.exit(1)

    result = {}
    for item in data:
        did = item.get("id")
        if not did:
            continue
        result[did] = item
    return result


def merge(ours_path: str, theirs_path: str, out_path: str) -> None:
    ours = _load(ours_path)
    theirs = _load(theirs_path)

    all_ids = set(ours) | set(theirs)
    merged: dict = {}

    only_ours = only_theirs = both_kept_ours = both_kept_theirs = 0

    for did in all_ids:
        if did in ours and did not in theirs:
            merged[did] = ours[did]
            only_ours += 1
        elif did in theirs and did not in ours:
            merged[did] = theirs[did]
            only_theirs += 1
        else:
            # Both have the drawer — keep the one with the newer timestamp.
            ts_ours = _parse_ts(ours[did].get("meta") or {})
            ts_theirs = _parse_ts(theirs[did].get("meta") or {})
            if ts_ours and ts_theirs and ts_ours > ts_theirs:
                merged[did] = ours[did]
                both_kept_ours += 1
            else:
                # Default: prefer theirs (remote is the canonical source)
                merged[did] = theirs[did]
                both_kept_theirs += 1

    # Sort by id for stable, diffable output
    result = sorted(merged.values(), key=lambda d: d["id"])

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = len(merged)
    print(
        f"merge_exports: {len(ours)} local + {len(theirs)} remote"
        f" => {total} unique drawers"
        f" (+{only_ours} local-only, +{only_theirs} remote-only,"
        f" {both_kept_ours} conflicts kept-ours, {both_kept_theirs} conflicts kept-theirs)"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge two mnemion drawer exports")
    parser.add_argument("--ours", required=True, help="Local export JSON path")
    parser.add_argument("--theirs", required=True, help="Remote export JSON path")
    parser.add_argument("--out", required=True, help="Output merged JSON path")
    args = parser.parse_args()
    merge(args.ours, args.theirs, args.out)
