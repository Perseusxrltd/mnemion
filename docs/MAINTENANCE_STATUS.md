# Automated maintenance status

Observed: 2026-10-26T07:43:48+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.13](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.13). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40285323866](https://github.com/Perseusxrltd/mnemion/actions/runs/40285323866) |
| public-updates\.yml | v4\.46\.13 | success | [Run 40268195296](https://github.com/Perseusxrltd/mnemion/actions/runs/40268195296) |
| release\.yml | release/4\.46\.13 | success | [Run 40262676121](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121) |
| release\.yml | release/4\.46\.14 | in\_progress | [Run 40286600426](https://github.com/Perseusxrltd/mnemion/actions/runs/40286600426) |
| verify-artifacts\.yml | main | success | [Run 40267817685](https://github.com/Perseusxrltd/mnemion/actions/runs/40267817685) |
| website-release\.yml | main | success | [Run 40285324108](https://github.com/Perseusxrltd/mnemion/actions/runs/40285324108) |
| website-release\.yml | v4\.46\.13 | success | [Run 40268192045](https://github.com/Perseusxrltd/mnemion/actions/runs/40268192045) |

## Active jobs

[Run 40286600426](https://github.com/Perseusxrltd/mnemion/actions/runs/40286600426): 15/21 jobs completed; 14 succeeded.

- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / ubuntu-22\.04 / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-2022 / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-11-arm / arm64: in\_progress — Run npm --prefix studio/frontend ci.
- native / macos-15 / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.

