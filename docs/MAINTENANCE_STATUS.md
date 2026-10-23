# Automated maintenance status

Observed: 2026-10-23T20:45:00+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.4](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.4). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40014217829](https://github.com/Perseusxrltd/mnemion/actions/runs/40014217829) |
| public-updates\.yml | v4\.46\.4 | success | [Run 40005404536](https://github.com/Perseusxrltd/mnemion/actions/runs/40005404536) |
| release\.yml | release/4\.46\.4 | success | [Run 39997298864](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864) |
| release\.yml | release/4\.46\.5 | failure | [Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734) |
| release\.yml | release/4\.46\.5-r2 | success | [Run 40013991029](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029) |
| verify-artifacts\.yml | main | in\_progress | [Run 40021524126](https://github.com/Perseusxrltd/mnemion/actions/runs/40021524126) |
| website-release\.yml | main | success | [Run 40014218141](https://github.com/Perseusxrltd/mnemion/actions/runs/40014218141) |
| website-release\.yml | v4\.46\.4 | success | [Run 40005399880](https://github.com/Perseusxrltd/mnemion/actions/runs/40005399880) |

## Active jobs

[Run 40021524126](https://github.com/Perseusxrltd/mnemion/actions/runs/40021524126): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.


## Unsuccessful jobs

- [Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734): native / windows-11-arm / arm64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
