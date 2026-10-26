# 4.46.13 native qualification and publication

**26 October 2026 publication checkpoint.**
[Release v4.46.13](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.13)
was published at **04:16:10 UTC**, with neither draft nor prerelease status.
The frozen source is
[`24db08327dbe916d834769a3e54a2acd59532bc8`](https://github.com/Perseusxrltd/mnemion/commit/24db08327dbe916d834769a3e54a2acd59532bc8).

## Installed targets

[Release workflow 40262676121](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121)
completed successfully at **04:11:56 UTC**. The original qualification receipt
at **04:12:46 UTC** binds workflow attempt 1, fresh artifacts, the frozen source
contract and **64 required true fields per target**:

| Installed target | Successful job | Required fields |
| --- | --- | ---: |
| Linux x64 | [121381324344](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121/job/121381324344) | 64/64 |
| Linux ARM64 | [121381324261](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121/job/121381324261) | 64/64 |
| Windows x64 | [121381324303](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121/job/121381324303) | 64/64 |
| Windows ARM64 | [121381324308](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121/job/121381324308) | 64/64 |
| macOS x64 | [121381324370](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121/job/121381324370) | 64/64 |
| macOS ARM64 | [121381324350](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121/job/121381324350) | 64/64 |

Windows ARM64 has a native ARM64 desktop with **emulated x64 engine and
database** components. The other five targets' architectures match natively.
The installed probe uses a new private profile and real model download. Its
checks include semantic save/recall, restart and recovery preservation, native
encrypted backups, protected credentials, capture and privacy controls.
Windows and macOS also passed their separate packaged update/relaunch steps.
These are distinct from public automatic-update qualification.

All six targets passed the five privacy-control fields: fixed synthetic format
preview, app/native choice visibility, preview clearing, no attempt during
inspection and opt-out persistence across restart. This is not exact-next-packet
inspection or active production telemetry. The earlier
[five-target 4.46.12 result](2026-10-26-telemetry-preview.md) and
[Intel Mac failures](2026-10-26-macos-release-reliability.md) remain preserved.

## Publication and deployment boundary

- [Artifact verification 40267817685](https://github.com/Perseusxrltd/mnemion/actions/runs/40267817685)
  passed at **04:16:20 UTC**.
- [Website release sync 40268192045](https://github.com/Perseusxrltd/mnemion/actions/runs/40268192045)
  passed at **04:16:31 UTC**.
- [Public automatic-update run 40268195296](https://github.com/Perseusxrltd/mnemion/actions/runs/40268195296)
  remained **in progress** at this checkpoint. Follow the generated
  [release status](../RELEASE_STATUS.md) for later gate results.

The original native receipt retains `public_release_acceptance: false` and
`l1_complete: false`; later publication does not rewrite its scope. The last
separately verified actual Windows/shared-host pair is
[4.46.6](2026-10-26-issue45-acceptance.md), including the 26 October read-only
version check. No 4.46.13 actual user update or new live backup acceptance follows
from these native/publication results.

All **66 requirement rows and state counts** remain unchanged. V08 remains
**Building**, with collection unavailable and destination/route null. Exact
packet inspection, production ingress/privacy and full telemetry resource,
wire and platform acceptance remain open. The subsequent Linux/macOS CPU-sensor
optimization is outside this frozen release.

Original six-target qualification receipt SHA-256:
`15c0b4d1d8acba4ee3d2ddd87fcea4c1e99559334254b974df365afdf7d2e91d`.
