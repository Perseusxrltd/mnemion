# 4.46.3 native qualification and publication

Qualified **23 October 2026 at 14:51:51 UTC** for frozen source
[`56e29f2c58d746170fa64bab09e7da91589efeee`](https://github.com/Perseusxrltd/mnemion/commit/56e29f2c58d746170fa64bab09e7da91589efeee),
branch `release/4.46.3`. [Release run 39961881757](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757)
completed successfully on **GitHub workflow attempt 2**. All six installed
targets ran freshly in that attempt and passed **59/59 required true fields**.
These are overlapping acceptance observations, not 59 independent tests.

| Installed target | Successful native job | Evidence artifact | Required fields |
| --- | --- | --- | --- |
| Linux x64 | [120452651269](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757/job/120452651269) | `12507901423` | 59/59 |
| Linux ARM64 | [120452651123](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757/job/120452651123) | `12507561559` | 59/59 |
| Windows x64 | [120452651182](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757/job/120452651182) | `12507293631` | 59/59 |
| Windows ARM64 | [120452651088](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757/job/120452651088) | `12509162856` | 59/59 |
| macOS x64 | [120452651259](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757/job/120452651259) | `12508349710` | 59/59 |
| macOS ARM64 | [120452651012](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757/job/120452651012) | `12507927186` | 59/59 |

The [complete qualification receipt](2026-10-23-4463-native-acceptance.json) is
copied **byte for byte**, SHA-256
`c16120529d86fced50a3df3a6b52c43875ee86c225922f8ba3df5873e27ec428`.
It binds the frozen source, workflow attempt, six source-contract hashes, job
and artifact IDs, downloaded archive digests and decoded evidence digests.
Saved job times and artifact metadata confirm each artifact was created within
its fresh attempt-two job. Its `release_attempt: 1` identifies the local release
plan; `workflow_attempt: 2` identifies the GitHub rerun.

## Installed scope

Each journey used a locally built installer, a new private profile and a real
model download. The observations cover setup, protected credentials, semantic
memory, encrypted backup/vault recovery, capture and offline intake, restart
continuity, authority/deletion fences and preservation of damaged state.
Windows ARM64 uses an ARM64 desktop with the tested **x64 engine/database
emulation**; the other targets use matching architectures.

All six jobs also passed their packaged window, sandboxed bridge and local-client
step. The probe requires actual host-control UI and native-agent schema checks,
including explicit backup approval and refusal of an unapproved backup request,
using **synthetic retained-copy inventory**. The protected host key and original
request survive an app restart; the probe inspects that request without replay
and enforces custodian and removal boundaries. Both Linux jobs additionally
passed encrypted workspace reconnect with a required real OS keyring.

Both Windows jobs passed the separate native installation, authenticated
upgrade and relaunch step. Both macOS jobs passed packaged update, restart
guards and relaunch. Linux has no separately listed update/relaunch step in
this receipt. These runner checks do not establish production host operations,
fresh independent Git-backup delivery or a replacement-host restore.

## Preserved attempt and recorder failures

Workflow attempt 1 failed after its
[macOS ARM64 database job 120442260979](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757/job/120442260979)
was cancelled with **no assigned runner and no executed steps**. The failure
annotation states: “The job was not acquired by Runner of type hosted even
after multiple attempts”; accompanying notices report macOS ARM capacity
constraints. GitHub Actions resumed failed jobs, producing workflow attempt 2
on the same frozen source. This is not evidence of a diagnosed product failure.

The original private native recorder stopped with
`Rerun artifact lineage needs separate qualification`. Its failure remains
retained. The reviewed qualifier verifies the exact completed attempt and
refuses mismatched source, reused jobs, or artifacts outside the job's time
window; the collected hashes bind the downloaded evidence. The original
cancelled-job metadata, annotations, recorder failure and later qualification
remain separate records. No source patch or native test rerun was performed
to prepare this documentation.

## Publication and actual-deployment boundary

[v4.46.3](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.3) was
published from this source at **14:50:04 UTC on 23 October**. Independent
artifact verification [39972316494](https://github.com/Perseusxrltd/mnemion/actions/runs/39972316494)
passed. A later check at **15:03 UTC** confirmed
[public-update workflow 39973022163](https://github.com/Perseusxrltd/mnemion/actions/runs/39973022163)
completed successfully, with all six platform/architecture jobs passed.
These public-installer update results are separate from actual-host acceptance.
Use the generated [release status](../RELEASE_STATUS.md) for evolving gate results.

The native JSON remains unchanged with `public_release_acceptance: false` and
`l1_complete: false`. Publication and later public-update evidence are separate
from its native-only scope.

The [actual 4.46.2 host rollback](2026-10-23-independent-host-adoption.md#4462-actual-host-rollback--23-october-2026)
and original 60-second startup diagnostics remain preserved. A read-only host
observation at **14:56:53 UTC** still reported **4.46.1**. The
[4.46.1 paired check](2026-10-23-4461-live-acceptance.md) remains the last accepted
actual pair. The existing guarded host-update job was dispatched at
**15:02:27 UTC** and its unit was **active/running** at the later checkpoint;
no host acceptance receipt was available. A running update job does not prove
successful cutover or service readiness. Actual Windows/shared-host 4.46.3
acceptance, the full two-custodian
lifecycle, fresh backup delivery and independent production restore remain
pending. Native qualification does not prove separate physical-device custody,
controller-authority escrow, whole-machine boot or provider wake.

All [66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) are unchanged.
[V08 product telemetry](../implementation/anonymous-product-telemetry.md) remains
Planned and inactive. The later [legacy vendor-telemetry correction](2026-10-23-legacy-vendor-telemetry.md)
is unreleased and **excluded from this frozen 4.46.3 source**.
