"""Scheduled local Obsidian refresh from the authenticated memory service."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from .sdk import Client


def refresh_from_config(path: Path, *, dry_run: bool = False) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(config, dict)
        or not isinstance(config.get("space_ids"), list)
        or not config["space_ids"]
    ):
        raise ValueError("Configure explicit space_ids for this vault")
    spaces = [str(UUID(value)) for value in config["space_ids"]]
    if len(spaces) > 20:
        raise ValueError("Refresh at most 20 spaces per vault configuration")
    vault, credentials_file = (
        Path(config["vault_path"]).expanduser(),
        Path(config["credentials_file"]).expanduser(),
    )
    if not vault.is_absolute() or not credentials_file.is_absolute():
        raise ValueError("Vault and credentials paths must be absolute")
    if not isinstance(config.get("review", False), bool):
        raise ValueError("review must be a boolean")
    credentials = json.loads(credentials_file.read_text(encoding="utf-8"))
    if not isinstance(credentials.get("api_key"), str) or not credentials["api_key"].startswith(
        "mnm_"
    ):
        raise ValueError("The private credentials file must contain an api_key")
    with Client(
        credentials.get("api_url", "http://127.0.0.1:7892"), credentials["api_key"]
    ) as client:
        return client.sync_obsidian(
            str(vault), spaces, review=config.get("review", False), dry_run=dry_run
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = refresh_from_config(args.config, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0 if result["completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
