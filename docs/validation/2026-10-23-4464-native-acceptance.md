# 4.46.4 native installer qualification

Qualified **23 October 2026 at 18:37:18 UTC** for frozen source
[`4e64aad45c288d2bc71146b976857225c628fb7a`](https://github.com/Perseusxrltd/mnemion/commit/4e64aad45c288d2bc71146b976857225c628fb7a),
branch `release/4.46.4`. [Release run 39997298864](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864)
completed successfully at **18:36:14 UTC**, on workflow attempt **1**.
All six installed targets passed **59/59 required true fields**. These are
overlapping acceptance observations, not 59 independent tests per target.

| Installed target | Successful native job | Evidence artifact | Required fields |
| --- | --- | --- | --- |
| Linux x64 | [120566901768](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864/job/120566901768) | `12521767466` | 59/59 |
| Linux ARM64 | [120566901812](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864/job/120566901812) | `12521452489` | 59/59 |
| Windows x64 | [120566901783](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864/job/120566901783) | `12521244123` | 59/59 |
| Windows ARM64 | [120566901920](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864/job/120566901920) | `12521984833` | 59/59 |
| macOS x64 | [120566901991](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864/job/120566901991) | `12522244639` | 59/59 |
| macOS ARM64 | [120566901947](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864/job/120566901947) | `12521592576` | 59/59 |

The original private `native/release-installed.receipt.json`, under the dated
`2026-10-23-inventory-privacy-4464` evidence directory, has SHA-256
`22618a5343339597d576398dbc7e4df3f2adcb64bff2cfb93b8aed1f98404798`.
Saved run, attempt, job and artifact metadata bind this frozen source and
confirm each artifact was created during its matching job. All six downloaded
archive and decoded-evidence hashes match the receipt; every required field
is true, and each archived JSON matches its decoded local copy. The original
receipt and evidence remain unchanged.

## Installed scope

Each journey used a locally built installer, a new private profile and a real
model download. It covers setup, protected credentials, semantic save/recall,
encrypted snapshots and vault recovery, capture/offline intake, restart
continuity, authority/deletion fences and preservation of damaged state.
Windows ARM64 uses the qualified x64 engine/database emulation; the other
targets use matching architectures.

All six saved jobs also passed their packaged window, sandboxed bridge and
local-client steps. Both Windows jobs passed the separate native installation,
authenticated upgrade and relaunch step; both macOS jobs passed packaged
update, restart guards and relaunch. No separate Linux update/relaunch step
is recorded here. These runner observations do not establish public-installer
upgrades, production backup delivery or an independent production restore.

The [4.46.4 source scope](../releases/4.46.4.md) contains the legacy vendor-telemetry
correction and backup-inventory optimization. The later
[4.46.5 transfer diagnostics and packing change](../releases/4.46.5.md) is
**excluded from this frozen source** and receives no qualification from this run.

## Public and actual-deployment boundary

At **18:38 UTC**, separate [artifact verification 40004648689](https://github.com/Perseusxrltd/mnemion/actions/runs/40004648689)
was still running, and the last observed public stable release remained 4.46.3.
This native receipt retains **`public_release_acceptance: false`** and
**`l1_complete: false`**. Publication, public-upgrade acceptance and an actual
Windows/shared-host 4.46.4 update require separate evidence. The generated
[release status](../RELEASE_STATUS.md) tracks changing public gates.

The last accepted actual pair and two-custodian lifecycle remain the separate
[4.46.3 paired check](2026-10-23-4463-live-acceptance.md) and
[custody journey](2026-10-23-4463-custody-acceptance.md). Earlier
[native failures](2026-10-23-4463-native-acceptance.md), the
[actual host rollback](2026-10-23-independent-host-adoption.md#4462-actual-host-rollback--23-october-2026)
and the [original backup failure](2026-10-23-backup-transfer-diagnostics.md)
remain preserved.

Separately, supported observe-only recovery completed at **18:10:36 UTC**;
the **18:14:03 UTC** receipt confirmed the existing 4.46.3 host was ready with
unchanged authority. The original backup is **failed/unconfirmed**, with
`operation_uncertain` retained. No new backup or service stop/start was
submitted, delivery was not verified, and independent restore had not started.
The private `2026-10-23-backup-transfer-recovery/recovery.receipt.json` has SHA-256
`061e8aae109ad316401dbd3dc5a9d6c00a4ca53f2d2c1b1d51348df13b0184ab`.
Its original connection-read failure and observation deadline remain preserved.

Fresh backup delivery and independent restore remain unaccepted. No
whole-machine boot, separate physical-device custody, provider wake or
controller-authority escrow is established here. All
[66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) are unchanged;
issues #44/#45 remain open, and [V08 product telemetry](../implementation/anonymous-product-telemetry.md)
remains Planned and inactive.
