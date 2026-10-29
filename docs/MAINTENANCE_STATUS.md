# Automated maintenance status

Observed: 2026-10-29T15:13:05+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.52](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.52). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (4)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#47](https://github.com/Perseusxrltd/mnemion/issues/47) | Field report \(4\.46\.40\): multi-agent usage audit — slow/hanging search, suspended connector scope, noisy activity log, unusable vault over MCP, and features left unused | 2026-10-28T17:01:24Z |
| [#48](https://github.com/Perseusxrltd/mnemion/issues/48) | Mnemion as the single system: full replacement of LEDGER/DISPATCH/files, plus vault compatibility | 2026-10-28T09:04:09Z |
| [#49](https://github.com/Perseusxrltd/mnemion/issues/49) | macOS Studio dies at launch: ad-hoc signature rejects Electron Framework | 2026-10-29T15:12:33Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40853583995](https://github.com/Perseusxrltd/mnemion/actions/runs/40853583995) |
| database-cache\.yml | main | success | [Run 40861058907](https://github.com/Perseusxrltd/mnemion/actions/runs/40861058907) |
| public-updates\.yml | v4\.46\.52 | success | [Run 40853494264](https://github.com/Perseusxrltd/mnemion/actions/runs/40853494264) |
| release\.yml | release/4\.46\.52 | success | [Run 40844389559](https://github.com/Perseusxrltd/mnemion/actions/runs/40844389559) |
| release\.yml | release/4\.46\.53 | in\_progress | [Run 40896509541](https://github.com/Perseusxrltd/mnemion/actions/runs/40896509541) |
| verify-artifacts\.yml | main | success | [Run 40852860198](https://github.com/Perseusxrltd/mnemion/actions/runs/40852860198) |
| website-release\.yml | main | success | [Run 40884273711](https://github.com/Perseusxrltd/mnemion/actions/runs/40884273711) |
| website-release\.yml | v4\.46\.52 | success | [Run 40853490883](https://github.com/Perseusxrltd/mnemion/actions/runs/40853490883) |

## Active jobs

[Run 40896509541](https://github.com/Perseusxrltd/mnemion/actions/runs/40896509541): 16/21 jobs completed; 14 succeeded.

- native / windows-11-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 40896509541](https://github.com/Perseusxrltd/mnemion/actions/runs/40896509541): native / macos-26 / arm64 (failure). Steps: Verify model custody with real native child processes, Retain generated desktop-content secret scan receipt.
