#!/usr/bin/env bash
# Only for disposable native CI runners, inside their own dbus-run-session.
set -euo pipefail
if [[ "${CI:-}" != true || "${RUNNER_OS:-}" != Linux ]]; then
  echo "Run this keyring fixture only on a disposable Linux CI runner." >&2
  exit 1
fi

# This is an ephemeral test keyring password, never a publisher or user secret.
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' | gnome-keyring-daemon --unlock --components=secrets >/dev/null
MNEMION_NATIVE_KEYRING_REQUIRED=1 npm --prefix studio/electron run smoke:packaged
