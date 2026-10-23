# 4.46.5 native installer qualification

Qualified **23 October 2026 at 20:45:26 UTC** for frozen source
[`8f022bd73ee364d681214a1b60421770c061e7e9`](https://github.com/Perseusxrltd/mnemion/commit/8f022bd73ee364d681214a1b60421770c061e7e9),
branch `release/4.46.5-r2`. [Release run 40013991029](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029)
completed successfully. This is **release candidate 2**, on GitHub workflow
attempt **1**. All six installed targets passed **59/59 required true fields**;
these are overlapping acceptance observations, not 59 independent tests per target.

| Installed target | Successful native job | Evidence artifact | Required fields |
| --- | --- | --- | --- |
| Linux x64 | [120624903784](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029/job/120624903784) | `12528962468` | 59/59 |
| Linux ARM64 | [120624903978](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029/job/120624903978) | `12528093855` | 59/59 |
| Windows x64 | [120624903760](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029/job/120624903760) | `12529970562` | 59/59 |
| Windows ARM64 | [120624903951](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029/job/120624903951) | `12529688953` | 59/59 |
| macOS x64 | [120624903969](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029/job/120624903969) | `12528569147` | 59/59 |
| macOS ARM64 | [120624903883](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029/job/120624903883) | `12528388250` | 59/59 |

The original qualification receipt has SHA-256
`7d1428c1509c943a3b7ccb6709a1cb21a39915ee414789f484e426f9c72effe1`.
Saved run, attempt, job and artifact metadata bind the exact source and show
each artifact was created during its matching job. All six archive and
decoded-evidence hashes match the receipt; every required field is true, and
each archived JSON matches its saved decoded copy. Original evidence is unchanged.

Each journey used a locally built installer, a new private profile and a real
model download. It covers setup, protected credentials, semantic save/recall,
encrypted snapshots and vault recovery, capture/offline intake, restart
continuity, authority/deletion fences and preservation of damaged state.
Windows ARM64 uses the qualified x64 engine/database emulation; other targets
use matching architectures. All six jobs also passed their packaged window,
sandboxed bridge and local-client steps. Both Windows jobs passed native
installation, authenticated upgrade and relaunch; both macOS jobs passed
packaged update, restart guards and relaunch. No separate Linux update/relaunch
step is recorded here.

The [first candidate's Windows ARM64 failure](2026-10-23-installed-workspace-open-diagnostics.md)
remains preserved: its workspace-opening guard expired after runtime startup
and the Open workspace click. The original artifact did not establish the
cause. The second candidate adds bounded failure classifications without
changing UI behavior, the 180-second opening guard or retry policy. Its later
native pass does not establish the original cause or prove a functional fix.

At the **20:45 UTC checkpoint**, separate
[artifact verification 40021524126](https://github.com/Perseusxrltd/mnemion/actions/runs/40021524126)
was still running. The native receipt retains **`public_release_acceptance: false`**
and **`l1_complete: false`**. Publication and public-upgrade acceptance require
separate evidence; the generated [release status](../RELEASE_STATUS.md) tracks
those gates. Native observations do not establish public-installer upgrades.

Subsequently, artifact verification and publication completed successfully.
[Release v4.46.5](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.5)
was published at **20:49:55 UTC**, bound to the same frozen source, with 38
assets. [Automatic website verification 40022240433](https://github.com/Perseusxrltd/mnemion/actions/runs/40022240433)
passed at **20:50:15 UTC**: the live product page showed the current version,
all six installer links, checksums, release notes, current guides and Git-owned
content, with the roadmap following main. Its retained receipt has SHA-256
`bc147d0873bffb9a06b537e1e6b725bc350e8919587cd560d68c14f5cbe57958`.
No website code or deployment change was required. These are separate public
observations; the original native receipt is unchanged.
[Public upgrade run 40022243634](https://github.com/Perseusxrltd/mnemion/actions/runs/40022243634)
was still running at the **20:56 UTC observation**, so no public-upgrade pass
is claimed at this checkpoint.

Actual Windows and the shared host still ran **4.46.3** at this checkpoint.
The accepted [paired check](2026-10-23-4463-live-acceptance.md) and
[two-custodian lifecycle](2026-10-23-4463-custody-acceptance.md) remain that
version's evidence. The [original failed/unconfirmed backup](2026-10-23-backup-transfer-diagnostics.md)
is preserved. The separate [isolated transfer and reviewed backup window](2026-10-23-backup-transfer-window-900.md)
do not establish a fresh native backup or independent restore. Those outcomes
and actual 4.46.5 paired acceptance await the qualified live sequence.

No whole-machine boot, separate physical-device custody, provider wake or
controller-authority escrow is established here. All
[66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) remain unchanged;
issues #44/#45 remain open, and [V08 product telemetry](../implementation/anonymous-product-telemetry.md)
remains Planned and inactive. The [release notes](../releases/4.46.5.md) describe
the qualified source scope.
