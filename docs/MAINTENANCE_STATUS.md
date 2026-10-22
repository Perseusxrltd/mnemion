# Automated maintenance status

Observed: 2026-10-22T22:22:27+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.45.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.45.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39859826761](https://github.com/Perseusxrltd/mnemion/actions/runs/39859826761) |
| public-updates\.yml | v4\.45\.0 | success | [Run 39843181077](https://github.com/Perseusxrltd/mnemion/actions/runs/39843181077) |
| release\.yml | release/4\.45\.0 | success | [Run 39829833717](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717) |
| release\.yml | release/4\.45\.1 | failure | [Run 39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596) |
| release\.yml | release/4\.45\.1-r2 | queued | [Run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559) |
| verify-artifacts\.yml | main | skipped | [Run 39864403901](https://github.com/Perseusxrltd/mnemion/actions/runs/39864403901) |
| website-release\.yml | main | success | [Run 39860935911](https://github.com/Perseusxrltd/mnemion/actions/runs/39860935911) |
| website-release\.yml | v4\.45\.0 | success | [Run 39843176416](https://github.com/Perseusxrltd/mnemion/actions/runs/39843176416) |

## Active jobs

[Run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559): 4/8 jobs completed; 3 succeeded.

- native / Encrypted files / Windows / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / Encrypted files / Windows / arm64: in\_progress — Set up job.
- native / native\_database / Private state / Windows / x64: in\_progress.
- native / native\_database / Private state / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.


## Unsuccessful jobs

- [Run 39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596): native / macos-15-intel / x64 (cancelled). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596): native / macos-15 / arm64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
