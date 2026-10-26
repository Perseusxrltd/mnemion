# Automated maintenance status

Observed: 2026-10-26T18:18:15+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.22](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.22). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40372658062](https://github.com/Perseusxrltd/mnemion/actions/runs/40372658062) |
| public-updates\.yml | v4\.46\.22 | success | [Run 40366545289](https://github.com/Perseusxrltd/mnemion/actions/runs/40366545289) |
| release\.yml | release/4\.46\.22 | success | [Run 40351425614](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614) |
| release\.yml | release/4\.46\.24 | in\_progress | [Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179) |
| verify-artifacts\.yml | main | success | [Run 40365617692](https://github.com/Perseusxrltd/mnemion/actions/runs/40365617692) |
| website-release\.yml | main | success | [Run 40372657882](https://github.com/Perseusxrltd/mnemion/actions/runs/40372657882) |
| website-release\.yml | v4\.46\.22 | success | [Run 40366540445](https://github.com/Perseusxrltd/mnemion/actions/runs/40366540445) |

## Active jobs

[Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179): 17/21 jobs completed; 14 succeeded.

- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15 / arm64: in\_progress — Packaged window, sandboxed bridge, and local client.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-2022 / x64: in\_progress — Native Windows installation, authenticated upgrade and relaunch.


## Unsuccessful jobs

- [Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179): native / ubuntu-22\.04 / x64 (failure). Steps: Package the native desktop with one bounded upstream-download retry.
- [Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179): native / ubuntu-22\.04-arm / arm64 (failure). Steps: Package the native desktop with one bounded upstream-download retry.
