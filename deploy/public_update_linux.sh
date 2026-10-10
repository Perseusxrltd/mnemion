#!/usr/bin/env bash
# A real window manager is needed for minimize/focus requests on the X11 desktop.
# Xvfb alone provides a display but cannot implement Studio's background window.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted || -z "${RUNNER_TEMP:-}" ]]; then
  echo 'Use a disposable GitHub-hosted Linux runner.' >&2
  exit 1
fi

openbox --sm-disable >"$RUNNER_TEMP/mnemion-window-manager.log" 2>&1 &
mnemion_wm_pid=$!
trap 'kill "$mnemion_wm_pid" 2>/dev/null || true; wait "$mnemion_wm_pid" 2>/dev/null || true' EXIT

mnemion_wm_ready=false
for mnemion_attempt in {1..100}; do
  if ! kill -0 "$mnemion_wm_pid" 2>/dev/null; then
    echo 'The test desktop window manager exited before launch.' >&2
    exit 1
  fi
  mnemion_wm_property=$(xprop -root _NET_SUPPORTING_WM_CHECK 2>/dev/null || true)
  if [[ "$mnemion_wm_property" == *'window id # 0x'* ]]; then
    mnemion_wm_ready=true
    break
  fi
  sleep 0.2
done
if [[ "$mnemion_wm_ready" != true ]]; then
  echo 'The test desktop did not acquire a window manager.' >&2
  exit 1
fi

python -m deploy.public_update_probe "$@"
