# Telemetry validation without discarded encodings

Date: 30 October 2026. Source follow-up to 4.46.55. Actual Windows Grok Build
authored `6dd670d529ace6f9e8b71b9e66e62ede62d50bef`; Astra reviewed the change,
removed a redundant return check, and ran the focused checks below.

## Change

Desktop workflow completion and paired resource samples must be validated
before they reach the recording port. Browser observations must also be
validated before waiting for a Web Lock or recording any member of a pair.
Those checks previously built encoded objects and cell arrays that were
immediately discarded.

The catalog now shares one validation walk between `observation()` and
`validateObservation()`. The latter counts cells without allocating the encoded
object or cell list. It retains numeric bounds, allowed fields, workflow and
metric families, outcome/reason compatibility, and the cell limit. Actual
encoding still happens at the storage boundary. Policy generations, input
copies, locks, SQLite lifetimes, sampling, delivery and wire coordinates are
unchanged. Validation still runs before IPC or the browser lock; invalid paired
observations cannot leave a submission behind.

## Verification

The Linux Node 22.22.0 review checkout passed:

- Electron TypeScript/native-helper build and frontend type checking.
- 75 native store/workflow/desktop-measurement checks; two unchanged Windows
  ACL checks were skipped on Linux.
- 35 browser policy checks, including rejection before IPC and lock acquisition.
- 24 client integration checks.
- All 27 Python/TypeScript v3 packet-parity cases.

Published v1/v2 coordinates and the tightened cell-limit fixture agree. Invalid
private fields, metric families, reasons, negative/non-finite values and unsafe
numbers are refused before recording. Valid observations still reach the port.
The generated inventory remains 96 mapped categories and zero unmeasured ones.

The first browser command passed its 35 policy checks but could not load the
client integration file: this checkout lacked `packages/client/dist/index.js`.
The existing client package was built, then only that unstarted integration
file was rerun; all 24 checks passed. The original failed log is retained. No
dependencies were installed and no passing policy suite was repeated.

## Limits

This removes known temporary allocations; it does not measure an RSS or CPU
improvement. No full resource or app journey was rerun. The earlier failed
resource evidence remains in the [resource report](2026-10-29-telemetry-v3-resource.md).
The 2 MiB and 0.5% gates, installed report delivery and production hosting/privacy
acceptance remain open. V08 remains Building and fleet collection stays disabled.
