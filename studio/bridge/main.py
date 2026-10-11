"""Packaged local operations for Studio's vault and OS-protected connections."""

import argparse
import json
import sys
from pathlib import Path

# The locked desktop environment deliberately does not install the server.
# Source launches resolve this checkout; frozen clients use their bundled modules.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mnemion.vault_client import sync_bundle
from mnemion.vault_refresh import VaultRefreshError
from mnemion.version import __version__
from mnemion.desktop_credentials import credential_request


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--credential", choices=["protect", "unprotect"])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--vault", type=Path)
    args = parser.parse_args(argv)
    if args.credential:
        if args.archive or args.vault or args.version:
            parser.error("Credential operations cannot be combined with other operations")
        try:
            result = credential_request(args.credential, sys.stdin.buffer.read(24577))
        except (ValueError, OSError) as exc:
            print(json.dumps({"error": "credential_unavailable", "message": str(exc)}))
            return 1
        print(json.dumps(result, ensure_ascii=True))
        return 0
    if args.version:
        print(json.dumps({"version": __version__, "capabilities": ["obsidian-refresh"]}))
        return 0
    if not args.archive or not args.vault:
        parser.error("--archive and --vault are required")
    try:
        if args.archive.stat().st_size > 120 * 1024**2:
            raise ValueError("Export archive is too large")
        result = sync_bundle(args.archive.read_bytes(), args.vault)
    except (ValueError, OSError, VaultRefreshError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    # A conflict is a completed local operation with an incomplete refresh.
    # The UI needs the structured conflict proposal, not a generic process error.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
