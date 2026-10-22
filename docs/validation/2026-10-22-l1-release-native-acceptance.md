# 4.45.0 frozen native installation acceptance

Qualified **22 October 2026, 19:27:34 UTC** for frozen source
`d8083b068ea0d6866747b8128b1edd8b5f256f69` in
[native release run 39829833717](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717). All six final **4.45.0**
installed targets passed the hosting and capture contract. Each qualified
receipt records **59 required true fields**; these are overlapping acceptance
observations, not a total of independent tests.

| Installed target | Frozen native evidence | Required fields | Separate packaged update/relaunch step |
| --- | --- | --- | --- |
| Linux x64 | [Native job](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717/job/120005209511) · artifact `12450211563` | 59/59 | Not separately listed in this receipt |
| Linux ARM64 | [Native job](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717/job/120005209654) · artifact `12450092246` | 59/59 | Not separately listed in this receipt |
| Windows x64 | [Native job](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717/job/120005209526) · artifact `12451085322` | 59/59 | Recorded pass |
| Windows ARM64 | [Native job](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717/job/120005209488) · artifact `12451483403` | 59/59 | Recorded pass |
| macOS x64 | [Native job](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717/job/120005209582) · artifact `12451980307` | 59/59 | Recorded pass |
| macOS ARM64 | [Native job](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717/job/120005209569) · artifact `12448604951` | 59/59 | Recorded pass |

Both Windows jobs record successful installation, authenticated upgrade and
relaunch. Both macOS jobs record successful packaged update, restart guards and
relaunch. The receipt does not separately list a Linux update step; it is not a
public-feed update receipt for any platform. Windows ARM64 uses an ARM64 desktop
with the documented **x64 engine and database emulation**. The other five targets
use matching desktop, engine and database architectures.

Each installed journey used a locally built installer, a new private profile and
real model download; model weights were not bundled. The frozen probe binds its
engine source and dependency hashes. The [qualification receipt](2026-10-22-l1-release-native-acceptance.json) records the
source-contract, artifact-archive and installed-evidence digests. Its SHA-256 is
`4b736da892907ba5b765bb7078a44d7ca620f320a08a10ea44d4b2af420fb4ca`.

The recorded fields cover actual app setup and protected account/key recovery;
approved retained capture, offline intake, Unicode/rotation and producer loss;
queue restart and lost-commit-reply reconciliation; current reader/device
authority and forgetting; reviewed policy replacement, damaged-inbox preservation
and quotas; independent packaged headless operation and recovery; and local
semantic memory, encrypted backup, vault and restart continuity. This is a
bounded installed journey, not a representative company-fleet capacity or
minimum-hardware measurement.

The [earlier candidate acceptance](2026-10-22-l1-candidate-acceptance.md) remains
bound to source `d3587263` and its own development artifacts. Those artifacts
identified themselves as 4.44.2 and were distinct from public 4.44.2. The
[actual-Codex shared-source journey](2026-10-22-shared-codex-capture.md) retains its
original `38eb3021` source and isolated environment; it is not a new live 4.45.0
migration. Earlier Windows path, runner and shared-source harness failures remain
in the [implementation history](../research/2026-10-21-durable-capture-implementation.md#current-installed-qualification).

**Publication and actual deployment remain separate evidence.** This native
receipt explicitly records `public_release_acceptance: false` and
`l1_complete: false`. It does not establish independent uploaded-asset/signature
verification, public downloads and update feeds, website delivery or the actual
Windows/shared-host migration. Use [generated release status](../RELEASE_STATUS.md)
for current public availability and release gates. The five capture migrations,
**030–034**, retain the [reviewed host-upgrade](../service/managed-upgrades.md),
independent backup and recovery requirements; this report records no live
migration or unattended Windows restart.

All [65 requirements](../PRODUCT_REQUIREMENTS.md) retain their statuses: **17
shipped, 42 partial, 2 planned, 3 ongoing and 1 external**. The first local-Codex
qualification does not complete broader provider/plugin history, inaccessible
records, attachment retrieval, general text-secret redaction, cross-device and
organization/source migration, fleet measurements or the remaining
[L1–L7 scope](../research/2026-10-20-layered-librarian.md). R07 remains planned.
Issues **44/45** remain open. The separate PC note-publisher pause remains in
force; native installation does not resume it.
