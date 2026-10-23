# 4.46.1 frozen native installation acceptance

Qualified **23 October 2026 at 08:30:55.386392 UTC** for frozen source
[`94684f002b707d6750edde2a00d7254f155f3eae`](https://github.com/Perseusxrltd/mnemion/commit/94684f002b707d6750edde2a00d7254f155f3eae),
branch `release/4.46.1-r2`. [Release run 39916372505](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505)
concluded **success**. All six installed hosting/capture receipts contain
**59/59 required true fields**. These are overlapping acceptance observations,
not a count of independent tests.

| Installed target | Successful native job | Evidence artifact | Required fields | Separate packaged update/relaunch |
| --- | --- | --- | --- | --- |
| Linux x64 | [120301587279](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505/job/120301587279) | `12487052983` | 59/59 | Not separately listed |
| Linux ARM64 | [120301587254](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505/job/120301587254) | `12487122257` | 59/59 | Not separately listed |
| Windows x64 | [120301587208](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505/job/120301587208) | `12488106754` | 59/59 | Passed |
| Windows ARM64 | [120301587210](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505/job/120301587210) | `12488972033` | 59/59 | Passed |
| macOS x64 | [120301587186](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505/job/120301587186) | `12488876885` | 59/59 | Passed |
| macOS ARM64 | [120301587330](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505/job/120301587330) | `12487961418` | 59/59 | Passed |

Windows ARM64 uses an ARM64 desktop with the tested **x64 engine and database
emulation**. The other five targets use matching desktop, engine and database
architectures. Both Windows jobs passed installation, authenticated upgrade and
relaunch; both macOS jobs passed packaged update, restart guards and relaunch.
These are runner checks; public-feed and actual customer updates remain separate.

The [qualification receipt](2026-10-23-4461-native-acceptance.json) is a complete,
unchanged copy of the collected receipt, SHA-256
`d06a3a8457927d495fe264558edf117eed29196a5908db15b4839a1e3238a492`.
It binds the run/source, six source-contract hashes, artifact IDs, downloaded
evidence-archive hashes and decoded evidence hashes. Those archives contain
installed-hosting observations, not installer distribution checksums. The frozen
probe also verifies engine source and dependency hashes; the small receipt does
not embed those manifests.

Each hosting journey used a locally built installer, a new private profile and
a real model download; model weights were not bundled. The observations cover
setup, protected account/key recovery, local semantic memory, encrypted
backup/vault recovery, retained capture, offline intake, authority/deletion
fences, restart continuity and damaged-state preservation.

## Packaged independent host controls

The saved job evidence confirms that all six platforms passed their **packaged
window, sandboxed bridge and local-client** step. Both Linux jobs also passed
**Linux encrypted workspace reconnect after process restart**, which reruns
the packaged journey with a required real OS keyring. These conclusions are
separate from the 59 hosting/capture observations.

The [frozen packaged probe](../../studio/electron/scripts/smoke-packaged-app.mjs)
requires the real host UI, protected per-device key, pinned SSH and native agent
pipe with the peer's memory API absent. A full app restart reopens the same key,
inspects the original queued request without replay, enforces the custodian
boundary and requires acknowledgement before archiving the public request and
removing the local key. The queued and retained requests must be visible in the
UI. These isolated client checks do not establish a production service stop,
watchdog integration or custody on independently held physical devices.

## Preserved Windows failure and corrected rebuild

The first [4.46.1 run 39913638457](https://github.com/Perseusxrltd/mnemion/actions/runs/39913638457)
used source `42aa7e0c0bbcad6f4d9bd8901c5695a9b264f95e`. Its
[Windows x64 job 120283946139](https://github.com/Perseusxrltd/mnemion/actions/runs/39913638457/job/120283946139)
failed at the journal repository URL field after ordinary creation, save and
semantic recall. The [journal-form record](2026-10-23-windows-journal-form.md)
preserves the original failure and the actual Chromium reproduction with
synthetic data. Moving the identity-bound draft reset to `useLayoutEffect`
kept the newly opened form; same-host refresh preserved the draft/review, while
a different host identity cleared them. Fixed diagnostic allowlists now name
the journal selector and route without arbitrary input or page text.

All six corrected installed receipts require
`nativeJournalRegistrationAndSeparateApproval: true`. The completed jobs above
supply the later rebuilt native qualification; the earlier browser report's
undispatched-native checkpoint remains historical. The original failed attempt
is preserved and has not been relabeled as a passing retry.

## Publication and deployment boundary

**Later publication checkpoint — 23 October 2026 at 08:46:59 UTC.**
[4.46.1](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.1), release
`421607105`, was published at **08:34:54 UTC** from the same frozen source.
The [generated status receipt](releases/4.46.1-status.json) records all five
release gates passed and 38 distribution assets. Independent verifier
[39925023152](https://github.com/Perseusxrltd/mnemion/actions/runs/39925023152)
recorded completed success at **08:35:02 UTC**.

[Public-update workflow 39925663475](https://github.com/Perseusxrltd/mnemion/actions/runs/39925663475)
completed successfully at **08:46:46 UTC**. All six Linux, Windows and macOS
x64/ARM64 jobs matched the frozen source and passed **Install public release
and observe its automatic update**. These public-installer runner journeys are
separate from acceptance on the actual Windows/shared-host pair. The
[website synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/39925659880)
also passed, recorded at **08:35:20 UTC**. Current availability and release gates
continue to follow [release status](../RELEASE_STATUS.md).

The qualification JSON remains byte-for-byte unchanged, retaining
`public_release_acceptance: false` and `l1_complete: false` for its original
native-only scope. The later public results above are separate evidence.
The [managed-startup measurements](2026-10-23-managed-startup.md), the preceding
[4.46.0 host rollback](2026-10-23-4460-live-rollout.md) and the last complete
[4.45.1 paired acceptance](2026-10-23-4451-live-acceptance.md) remain separate
evidence. At this checkpoint the actual Windows app is **4.46.1**, while the
shared host is still performing its pre-update backup. Actual shared-host
4.46.1 readiness and paired acceptance, fresh independently verified production
backup, host-controller adoption, two-custodian operations, whole-machine boot
and provider wake still require their own acceptance. Broader
[L1–L7 work](../research/2026-10-20-layered-librarian.md) remains open.
All [66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) are unchanged.
[V08 telemetry](../implementation/anonymous-product-telemetry.md) remains Planned
and outside this release.
