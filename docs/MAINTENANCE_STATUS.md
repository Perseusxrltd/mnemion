# Automated maintenance status

Observed: 2026-10-23T07:38:18+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39916297399](https://github.com/Perseusxrltd/mnemion/actions/runs/39916297399) |
| public-updates\.yml | v4\.46\.0 | success | [Run 39907316827](https://github.com/Perseusxrltd/mnemion/actions/runs/39907316827) |
| release\.yml | release/4\.46\.0-r2 | success | [Run 39895069093](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093) |
| release\.yml | release/4\.46\.1 | failure | [Run 39913638457](https://github.com/Perseusxrltd/mnemion/actions/runs/39913638457) |
| release\.yml | release/4\.46\.1-r2 | queued | [Run 39916372505](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505) |
| verify-artifacts\.yml | main | skipped | [Run 39919030121](https://github.com/Perseusxrltd/mnemion/actions/runs/39919030121) |
| website-release\.yml | main | success | [Run 39916297432](https://github.com/Perseusxrltd/mnemion/actions/runs/39916297432) |
| website-release\.yml | v4\.46\.0 | success | [Run 39907323013](https://github.com/Perseusxrltd/mnemion/actions/runs/39907323013) |

## Active jobs

[Run 39916372505](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505): 4/19 jobs completed; 3 succeeded.

- checks / lint: in\_progress — Retain source scan receipt without matched content.
- checks / studio: in\_progress — Check the lightweight native client before six-platform packaging.
- native / Encrypted files / Windows / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / Encrypted files / Windows / arm64: in\_progress — Set up job.
- checks / dependency-audit: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- checks / container \(ubuntu-22\.04\): in\_progress — Set up job.
- checks / legacy: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- checks / supervision \(macos-15\): in\_progress.
- checks / service \(3\.13\): in\_progress — Initialize containers.
- checks / container \(ubuntu-22\.04-arm\): queued.
- checks / service \(3\.14\): in\_progress — Set up job.
- checks / supervision \(macos-15-intel\): queued.
- checks / service \(3\.12\): in\_progress — Initialize containers.
- native / native\_database / Private state / Windows / arm64: in\_progress — Set up job.
- native / native\_database / Private state / Windows / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.


## Unsuccessful jobs

- [Run 39913638457](https://github.com/Perseusxrltd/mnemion/actions/runs/39913638457): native / windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
