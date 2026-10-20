# Existing folder identity during desktop reconnection

Recorded 20 October 2026. Prepared candidate: **4.42.0**. The repair has passed
focused source checks and the normal version/contract preparation. Native
installers, publication and actual provider acceptance remain separate gates;
see the generated [release status](../RELEASE_STATUS.md) for delivery results.

## Reproduced failure and repair

An isolated PostgreSQL workspace and real HTTP service reproduced a failure in
4.41.0 / `fca12c7`. A CLI folder source already existed as
`filesystem:established-office`. Reconnecting its folder through Studio's helper
used the hardcoded `filesystem:selected-source`, created a second source and
suspended the original as `access_lost`. Its original reader could no longer
fetch the memory, although the scan reported completion and one change.

The repair resolves the existing connector's single filesystem namespace during
verification and before each scan. A new connection retains the default.
An optional custom `scope_id` survives private settings and agent status; the
ordinary default remains implicit for compatibility with existing settings.
An explicit mismatch, malformed catalog or ambiguous catalog prevents import. The app
explains selecting the genuine folder or restored copy and stopping the prior
runner. These checks retain normal source mappings and access revalidation.

The corrected reproduction kept one source, its original space and memory,
and the reader's access. It reported completion with zero redundant changes and
no suspension. An additional mapped reader gained access only after an actual
folder scan; the original reader remained authorized and the administrator did
not acquire implicit content access.

## Evidence and limits

- **14 focused Python cases passed**, including real PostgreSQL/HTTP identity
  and reader revalidation, unchanged memory/revision behavior, ambiguity and
  mismatch refusal, old/new private-state round trips and existing capture.
- **8 Electron control cases passed**. The client, Electron and frontend
  production builds also passed. These are source/control checks, not a new
  six-platform installed-app or production-provider walkthrough.
- The isolated tests made **zero production requests** and no production grants,
  scans or publisher changes. No cloud-model call or paid service was used.
- All **65 requirement IDs and statuses remain unchanged**. This repair advances
  source continuity and access correctness without closing either broader scope.

Private evidence is retained under
`mnemion-completion/2026-10-20-source-identity-recovery/`:
`original-reproduction.log`, `original-observation.json`,
`corrected-reproduction.json`, `corrected-reproduction.log`,
`focused-python.log`, `focused-electron.log`, `focused-python-final.log` and
`focused-electron-final.log`. The final runs retain 14 Python and 8 Electron
passes after preserving the ordinary default's existing private-file format.
The original failing pytest log remains unchanged. The first corrected run
reused the diagnostic JSON filename; `original-observation.json` therefore
identifies its fields as recovered from captured original output, while the
corrected result is stored separately. The original diagnostic JSON is not
claimed to be an immutable original artifact.

[Issue 46](https://github.com/Perseusxrltd/mnemion/issues/46) remains open until the
actual providers and mapped access revalidate. Reconnecting an available folder
does not recover an offline host's full source data, transfer credentials or
provide arbitrary host/runner takeover. The upstream local-note publisher's
security pause remains in force. See the [operator guide](../service/desktop-sources.md#reconnect-an-existing-folder)
and [release status](../RELEASE_STATUS.md) for the separate operating and delivery
boundaries.
