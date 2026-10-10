#!/usr/bin/env bash
# Shared memory is authoritative in the service. This job refreshes Obsidian.
set -euo pipefail
if [ -z "${MNEMION_VAULT_CONFIG:-}" ]; then
    echo "Set MNEMION_VAULT_CONFIG to an Obsidian refresh configuration. Legacy Git memory sync is retired; see sync/README.md." >&2
    exit 2
fi
MNEMION_SYNC_PYTHON="${MNEMION_PYTHON:-python3}"
exec "$MNEMION_SYNC_PYTHON" -m mnemion.vault_sync --config "$MNEMION_VAULT_CONFIG" "$@"
