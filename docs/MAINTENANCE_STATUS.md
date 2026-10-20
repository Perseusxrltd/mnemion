# Automated maintenance status

Observed: 2026-10-20T17:12:22+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.41.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.41.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39460842888](https://github.com/Perseusxrltd/mnemion/actions/runs/39460842888) |
| public-updates\.yml | v4\.41\.0 | success | [Run 39441745467](https://github.com/Perseusxrltd/mnemion/actions/runs/39441745467) |
| release\.yml | release/4\.41\.0 | success | [Run 39428746847](https://github.com/Perseusxrltd/mnemion/actions/runs/39428746847) |
| release\.yml | release/4\.42\.0 | failure | [Run 39457153644](https://github.com/Perseusxrltd/mnemion/actions/runs/39457153644) |
| release\.yml | release/4\.43\.0 | queued | [Run 39460885775](https://github.com/Perseusxrltd/mnemion/actions/runs/39460885775) |
| verify-artifacts\.yml | main | skipped | [Run 39463757862](https://github.com/Perseusxrltd/mnemion/actions/runs/39463757862) |
| website-release\.yml | main | success | [Run 39460842819](https://github.com/Perseusxrltd/mnemion/actions/runs/39460842819) |
| website-release\.yml | v4\.41\.0 | success | [Run 39441738346](https://github.com/Perseusxrltd/mnemion/actions/runs/39441738346) |

## Active jobs

[Run 39460885775](https://github.com/Perseusxrltd/mnemion/actions/runs/39460885775): 8/13 jobs completed; 7 succeeded.

- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- native / native\_database / Database / windows / x64: in\_progress — Relocate, initialize, verify TLS and RLS, restore backup and recover a crash.
- native / native\_database / Database / macos / x64: in\_progress — Relocate, initialize, verify TLS and RLS, restore backup and recover a crash.
- native / native\_database / Database / macos / arm64: queued.
- native / native\_database / Database / linux / arm64: in\_progress — Run actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02.


## Failed jobs

- [Run 39457153644](https://github.com/Perseusxrltd/mnemion/actions/runs/39457153644): native / windows-2022 / x64. Steps: Installed app creates, searches and reopens a real local workspace.
