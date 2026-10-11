# Memory map and connection validation

Date: **2026-10-11**. Version **4.0.10** was published at **09:08 UTC** after
the implementation checks below, all six native package gates and independent
verification of the uploaded release files. Source UI journeys and native
installer/update checks are identified separately.

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

## Publication and cross-platform checks

- [Product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38126210499)
  passed, including Python 3.12/3.13/3.14 service checks, legacy compatibility,
  SDK/UI builds, dependency audits and native managed-service checks on both Macs.
- [Native desktop checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38126210504)
  and the [release workflow](https://github.com/Perseusxrltd/mnemion/actions/runs/38126221958)
  passed for Windows, macOS and Linux, x64 and ARM64. Gates include the packaged
  app, private bridge, update guards and platform-specific installation/relaunch.
- The release targets commit `dea415219e32d214a1a89d5fd4966b004dc468b9`.
  All **38 uploaded assets** were downloaded and their sizes and SHA-256 hashes
  matched GitHub's digests and `SHA256SUMS.txt`. The verifier independently checked
  service and Windows/macOS signatures against the embedded production keys,
  complete update feeds and packaged web file inventories.
- [4.0.10 is public](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.0.10).
  [Release metadata synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/38127301902)
  passed automatically. A real browser verified that the existing live
  [product page](https://www.perseusxr.com/mnemion) adopted 4.0.10, all six download
  links, current notes/checksums/guides and the live roadmap without a website
  edit or redeployment. Desktop and 390-pixel layouts had no horizontal overflow
  or browser errors; the homepage still linked to the product with the same logo.
- The [public 4.0.9 → 4.0.10 update rehearsal](https://github.com/Perseusxrltd/mnemion/actions/runs/38127301901)
  started automatically after publication. Its result is separate from the
  passing native fixture gates and was pending when this publication record
  was written.

## Remaining limitations

This first map polls bounded snapshots, not deltas. It does not show every event
in a large workspace, infer semantic similarity from geometry, provide time
replay, repair an offline host, or provide a new hosted provider login. Track
those separately in the [requirements](../PRODUCT_REQUIREMENTS.md) and
[map guide](../service/memory-map.md). The public Linux x64 4.0.8 → 4.0.9 restart
issue and native local-host provisioning remain open work.
