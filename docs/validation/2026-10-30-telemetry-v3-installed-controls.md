# Installed 4.46.55 telemetry controls

**30 October local; qualification completed 29 October 2026 at 23:35:59 UTC.**
The original [4.46.55 release run](https://github.com/Perseusxrltd/mnemion/actions/runs/40965130140)
qualifies the installed privacy controls on Linux, Windows and macOS, each on
x64 and ARM64. The source is
[`da8e97bc`](https://github.com/Perseusxrltd/mnemion/commit/da8e97bc362c90427f690bd4f970e5f3a710c9a6).
This review read the existing installer artifacts. It ran no new build, app
journey or model call.

Each target passed 67 required hosting fields, including eight telemetry
fields. These are eight control assertions within a larger installed journey,
not 67 independent telemetry tests. The
[machine-readable qualification](2026-10-30-telemetry-v3-installed-controls.json)
preserves the original job and artifact IDs, archive and evidence digests, and
frozen probe hashes. All six artifacts were created during their successful
jobs in workflow attempt 1.

## What passed

| Installed behavior | Evidence |
| --- | --- |
| Fresh disclosure and format preview | The saved preference starts enabled, effective collection is false and disclosure is zero. The actual privacy UI renders the exact 25-byte v3 synthetic example and its privacy labels. No outgoing report is claimed. |
| App and agent choice | App opt-out is visible through the native bridge. Agent preference editing does not acknowledge an unseen disclosure or enable collection. |
| Refresh | Focus refresh reads the agent's saved choice and removes the old displayed preview. |
| Inspection without an attempt | Final pending records and recorded weekly delivery attempts are zero. This assertion is not packet-capture evidence. |
| Opt-out after restart | The next clean app launch retains opt-out, ineffective collection and an empty queue. |
| Review before permission | Manual-review mode saves without collection permission. No report exists; inspect, approve and discard remain disabled. |
| App and agent review mode | Both interfaces change review mode and the app reflects the native choice. |
| Review mode after restart | Manual mode survives with no packet, report or recorded attempt. |

The frozen native privacy probe exercises the actual installed UI and typed
bridge in an isolated profile. The smoke runner closes that app cleanly; the
following hosting phase checks the saved opt-out and review mode before setup.
Windows ARM64 runs its ARM64 desktop with the declared x64 service/database
compatibility components. The other five targets have matching native
architectures.

## Receipt-reader correction

The first local qualification stopped because its Mac ARM job-name lookup
still expected `macos-15`. The frozen release used `macos-26`; its original
installed job had succeeded. The reader now extracts the literal target matrix
from the frozen source and checks its relationship to the frozen workflow,
without executing that selector. It still requires the exact job, platform,
architecture, source, successful step, artifact digest and attempt lineage.

Nine focused checks passed: the six actual job names, historical Mac runner
compatibility, and refusal of missing/duplicate targets, a runner/platform
mismatch, an unsupported architecture, a computed matrix, changed job naming
and a different selector. The same original artifacts then qualified. Both the
first reader failure and corrected result remain retained; no platform test
was retried or relabeled.

## Remaining acceptance

These controls do not stage, approve or send a real report. Installed delivery,
whole-wire cost, resource limits, sensor coverage and production
collector/ingress privacy remain open. Collection/destination/route remain
false/null/null; V08 remains Building and all 66 requirements remain.

The earlier [4.46.22 control evidence](2026-10-26-telemetry-installed-review.md)
keeps its own scope and original attempts. Current publication and independent
public update checks are maintained in [release status](../RELEASE_STATUS.md).
