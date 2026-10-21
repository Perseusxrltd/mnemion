# Automated maintenance status

Observed: 2026-10-21T12:43:43+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.44.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.44.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39598649170](https://github.com/Perseusxrltd/mnemion/actions/runs/39598649170) |
| database-cache\.yml | main | success | [Run 39576347122](https://github.com/Perseusxrltd/mnemion/actions/runs/39576347122) |
| desktop\.yml | main | in\_progress | [Run 39598747700](https://github.com/Perseusxrltd/mnemion/actions/runs/39598747700) |
| public-updates\.yml | v4\.44\.0 | success | [Run 39534394111](https://github.com/Perseusxrltd/mnemion/actions/runs/39534394111) |
| release\.yml | release/4\.44\.0 | success | [Run 39530357580](https://github.com/Perseusxrltd/mnemion/actions/runs/39530357580) |
| verify-artifacts\.yml | main | success | [Run 39534260688](https://github.com/Perseusxrltd/mnemion/actions/runs/39534260688) |
| website-release\.yml | main | success | [Run 39598867307](https://github.com/Perseusxrltd/mnemion/actions/runs/39598867307) |
| website-release\.yml | v4\.44\.0 | success | [Run 39534391338](https://github.com/Perseusxrltd/mnemion/actions/runs/39534391338) |

## Active jobs

[Run 39598747700](https://github.com/Perseusxrltd/mnemion/actions/runs/39598747700): 12/18 jobs completed; 12 succeeded.

- windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.

