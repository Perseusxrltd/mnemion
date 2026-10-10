#!/usr/bin/env python3
"""Retired v3 union merge entry point: a JSON union cannot preserve deletion."""

import argparse


def merge(ours_path: str, theirs_path: str, out_path: str) -> None:
    raise ValueError(
        "Automatic drawer unions are retired: they can resurrect deleted data and discard trust history. "
        "Use mnemion-service legacy-backup/legacy-restore for preservation and the authenticated service for shared memory."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ours", required=True)
    parser.add_argument("--theirs", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        merge(args.ours, args.theirs, args.out)
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")
