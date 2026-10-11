# Memory map and connection validation

Date: **2026-10-11**. These checks validate the implementation for the next patch
after 4.0.9. They do not relabel an unreleased source build as a public installer.

## Connection diagnosis

- 21 agent-control/diagnostic tests passed, including bounded/trickled responses,
  redirect refusal, no credentials on public health requests, private SSE session
  cleanup and reports that omit keys, names and untrusted proxy responses.
- The Python SDK/client suite passed after correcting a new test's method call;
  the real HTTP/MCP diagnostic passed against an isolated PostgreSQL service.
- Eight TypeScript SDK tests passed, including explicit offline-tunnel handling.
- A read-only check of an existing remote connection returned ngrok
  `ERR_NGROK_3200`. Its host could not be reached. No memory operation, host
  restart or credential change occurred; no private address/key is published.

## Live map

- Five model tests cover stable geometry across additions/reordering, creator
  and time filters, bounded node selection, endpoint-safe edges, stale selections
  after access removal and actual 3D projection versus the flat fallback.
- A Chromium browser journey used a real local API and PostgreSQL database with
  36 synthetic memories written by three scoped application identities.
- The journey exercised orbit/keyboard controls, 2D mode, creator selection,
  subject search, focused evidence and opening the original memory history.
- A real API write appeared through the 20-second refresh. Pausing stopped
  polling; idle rendering performed no repeated canvas clears.
- A contributor could view accessible knowledge but made no reviewer-only
  activity request. Revoking its space grant and refreshing removed the map.
- Reduced-motion preferences selected 2D. The 390-pixel layout fit the viewport
  without horizontal overflow. No external visualization request or browser
  exception occurred.
- A separate **Linux Electron source-build** journey used the real encrypted-key
  broker's opaque renderer session, full-screen map, source evidence and proper
  disconnect. Read-only filters allowed update safety; a real unsaved text field
  continued to block unattended restart until removed. The canonical SVG loaded.
- Production frontend compilation and all 47 Electron unit tests passed.
  Native packaged smoke checks now also exercise the read-only-filter exception
  while preserving unsaved-draft protection.

Screenshots and fixture credentials stayed in the local validation workspace.
The fixture is not retrieval-quality evidence and did not download a model.

## Remaining gates and limitations

The preceding branding/connection commit passed product checks and all six native
desktop checks. The map itself still needs its corresponding complete native
packaging/release run before public availability. The published version remains
4.0.9 until that release is complete.

This first map polls bounded snapshots, not deltas. It does not show every event
in a large workspace, infer semantic similarity from geometry, provide time
replay, repair an offline host, or provide a new hosted provider login. Track
those separately in the [requirements](../PRODUCT_REQUIREMENTS.md) and
[map guide](../service/memory-map.md). The public Linux x64 4.0.8 → 4.0.9 restart
issue and native local-host provisioning remain open work.
