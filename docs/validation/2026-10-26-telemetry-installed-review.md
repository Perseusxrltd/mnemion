# Installed 4.46.22 privacy-review controls

**26 October 2026, existing-artifact qualification at 18:04:41 UTC.** The
original [release run 40351425614](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614)
provides six-target installed evidence for version **4.46.22**, source
[`2d48ace846f346a95b2a57559dc95affdbc42e91`](https://github.com/Perseusxrltd/mnemion/commit/2d48ace846f346a95b2a57559dc95affdbc42e91).
The unchanged qualifier checked already-produced artifacts. This qualification
performed **zero new builds, app runs or model calls**.

## Original attempts and artifact freshness

Each selected artifact is fresh in its own workflow attempt and was created
during its successful job. The qualifier binds source, native runtime, artifact
lineage/digests, job timing and the original installed-probe contract. All six
targets pass **67 required hosting fields, including exactly eight telemetry
fields**. These are not 67 independent telemetry tests.

| Target | Original workflow attempt | Successful job | Artifact |
| --- | ---: | --- | ---: |
| Linux x64 | 1 | [121675589718](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614/job/121675589718) | 12665582872 |
| Linux ARM64 | 1 | [121675589777](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614/job/121675589777) | 12664733812 |
| Windows x64 | 1 | [121675589560](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614/job/121675589560) | 12666191965 |
| Windows ARM64 | 1 | [121675589504](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614/job/121675589504) | 12667853588 |
| macOS x64 | 1 | [121675589461](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614/job/121675589461) | 12666268742 |
| macOS ARM64 | 2 | [121703380937](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614/job/121703380937) | 12670395683 |

Attempt 1 remains a **failed workflow**: its Mac ARM job
[121675589488](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614/job/121675589488)
was cancelled for hosted-runner capacity without steps or an assigned runner.
The later single-job capacity retry supplied Mac ARM's attempt-2 evidence. The
five successful attempt-1 targets were not rerun or relabeled as attempt 2.
Neither individual receipt claims all six targets within its own attempt.

Windows ARM64 uses a native ARM64 desktop with emulated x64 engine/database
components; the other five targets' architectures match natively. The original
hosting journeys also exercised model and hosting operations. This report credits
only the telemetry-control evidence below, without repeating those journeys.

## What the installed controls demonstrate

The frozen [privacy probe](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/native-telemetry-probe.ts)
uses the actual installed privacy UI and typed native bridge in a new private
profile. The [installed smoke runner](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/scripts/smoke-installed-hosting.mjs)
requires the control fields, closes the app cleanly and launches its next phase.
The [hosting probe](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/local-hosting-probe.ts)
then checks persisted opt-out and manual-review mode before local setup.

| Required telemetry field | Demonstrated boundary |
| --- | --- |
| `nativeTelemetryDisclosurePreview` | New-profile preference is enabled, effective collection is false and disclosure version is zero. The UI renders synthetic `AgAHAA==`; actual outbound body is null, bytes zero and state `not_inspected`. |
| `nativeTelemetryAppAgentChoice` | App opt-out is visible through the native API. Native preference editing does not acknowledge disclosure or enable collection. |
| `nativeTelemetryPreviewClearedOnRefresh` | Focus-triggered refresh reflects the native choice and clears the old displayed preview. |
| `nativeTelemetryNoAttemptDuringInspection` | Final pending records and recorded weekly delivery attempts are zero. This is not packet-capture evidence. |
| `nativeTelemetryOptOutSurvivesRestart` | Opt-out, ineffective collection and an empty pending queue survive the probe's clean app restart. |
| `nativeTelemetryReviewBeforePermission` | Manual mode saves without consent; no report or packet exists, and inspect/approve/discard controls remain disabled. |
| `nativeTelemetryReviewAppAgentChoice` | UI manual-mode selection and native API automatic-mode selection round-trip through the app; the UI then saves manual mode again. |
| `nativeTelemetryReviewModeSurvivesRestart` | Manual mode survives restart with no report, packet or recorded delivery attempt. |

The final three fields add review-control evidence to the five basic privacy
fields previously qualified for [4.46.13](2026-10-26-44613-native-acceptance.md).
No report was staged, approved or delivered in these installed checks.

## Retained proof and remaining gates

`installed-review-acceptance.json` combines the two original receipts and retains
each artifact/evidence digest and frozen source copy. Its SHA-256 is
`500518a71150bfb051a9fbf0269585f8d4c9d2491abe0edf06b09c8567e131fd`.
The separate receipt hashes remain:

- `attempt-1/installed-review-1.receipt.json`:
  `a5d6f30b0228ddba024ccbe1dbc0fc2b59431fbba31e11b706ca4f9133e1ab80`.
- `attempt-2/installed-review-2.receipt.json`:
  `a651b0bb15a5431010ef669b7704cab032bb25e50fb7c41d030c2ea93d3762d7`.

Raw historical attempt responses, the failed attempt, job/artifact metadata,
archives and qualifier logs remain preserved. Both receipts retain
`public_release_acceptance: false` and `l1_complete: false`; their combination
does not expand those scopes.

Installed staging, approval and delivery of an actual report remain unqualified.
This evidence does not qualify later owner changes, 4.46.25 installed behavior,
resource/whole-wire bounds, provider/ingress privacy, full V08 or an actual PC/VPS
upgrade. Release availability and independent update gates remain in
[release status](../RELEASE_STATUS.md).

All **66 requirement texts and states** remain unchanged. V08 stays **Building**,
with collection unavailable and destination/route null. Policy, resource budgets,
runtime and version declarations were not changed for this evidence qualification.
