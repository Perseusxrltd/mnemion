# Automated maintenance status

Observed: 2026-10-20T17:11:34+00:00. Updated by repository events and the scheduled status workflow.

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
| release\.yml | release/4\.43\.0 | in\_progress | [Run 39460885775](https://github.com/Perseusxrltd/mnemion/actions/runs/39460885775) |
| verify-artifacts\.yml | main | skipped | [Run 39463757862](https://github.com/Perseusxrltd/mnemion/actions/runs/39463757862) |
| website-release\.yml | main | success | [Run 39460842819](https://github.com/Perseusxrltd/mnemion/actions/runs/39460842819) |
| website-release\.yml | v4\.41\.0 | success | [Run 39441738346](https://github.com/Perseusxrltd/mnemion/actions/runs/39441738346) |

## Active jobs

[Run 39460885775](https://github.com/Perseusxrltd/mnemion/actions/runs/39460885775): 4/8 jobs completed; 3 succeeded.

- native / Encrypted files / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / Encrypted files / Windows / x64: in\_progress — Run python -m pip install pytest cryptography==50\.0\.2.
- native / native\_database / Private state / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Private state / Windows / x64: in\_progress — Install small private-state test dependencies.


## Failed jobs

- [Run 39457153644](https://github.com/Perseusxrltd/mnemion/actions/runs/39457153644): native / windows-2022 / x64. Steps: Installed app creates, searches and reopens a real local workspace.
