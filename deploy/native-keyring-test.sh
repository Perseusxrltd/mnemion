#!/usr/bin/env bash
# Only for disposable native CI runners, inside their own dbus-run-session.
set -euo pipefail
if [[ "${CI:-}" != true || "${RUNNER_OS:-}" != Linux ]]; then
  echo "Run this keyring fixture only on a disposable Linux CI runner." >&2
  exit 1
fi

# This is an ephemeral test keyring password, never a publisher or user secret.
MNEMION_KEYRING_FIXTURE="$(mktemp -d "${RUNNER_TEMP:?}/mnemion-keyring.XXXXXXXX")"
mkdir -p "$MNEMION_KEYRING_FIXTURE/data" "$MNEMION_KEYRING_FIXTURE/control"
trap 'rm -rf -- "$MNEMION_KEYRING_FIXTURE"' EXIT
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' | XDG_DATA_HOME="$MNEMION_KEYRING_FIXTURE/data" \
  gnome-keyring-daemon --unlock --components=secrets --control-directory="$MNEMION_KEYRING_FIXTURE/control" >/dev/null
case "${1:-packaged}" in
  packaged) MNEMION_NATIVE_KEYRING_REQUIRED=1 npm --prefix studio/electron run smoke:packaged ;;
  installed-hosting) MNEMION_NATIVE_KEYRING_REQUIRED=1 npm --prefix studio/electron run smoke:installed-hosting ;;
  *) echo "Unknown native keyring validation mode." >&2; exit 1 ;;
esac
