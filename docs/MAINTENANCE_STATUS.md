# Automated maintenance status

Observed: 2026-10-19T21:30:26+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.24.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.24.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds are checked for failed jobs at each observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (5)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#3](https://github.com/Perseusxrltd/mnemion/issues/3) | No built-in remote access option; operators must bring their own reverse proxy / tunnel | 2026-10-11T03:04:30Z |
| [#4](https://github.com/Perseusxrltd/mnemion/issues/4) | No OAuth for hosted agents; static bearer tokens only | 2026-10-10T20:55:33Z |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |
| [#38](https://github.com/Perseusxrltd/mnemion/issues/38) | Host reset wipes a self-hosted install with no reproducible re-install path or off-host key/state recovery | 2026-10-19T12:13:43Z |
| [#39](https://github.com/Perseusxrltd/mnemion/issues/39) | Buffer memory with automatic additive write-back to Git \(native saves are never pushed upstream\) | 2026-10-19T11:44:25Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39322011010](https://github.com/Perseusxrltd/mnemion/actions/runs/39322011010) |
| public-updates\.yml | v4\.24\.0 | success | [Run 39315350141](https://github.com/Perseusxrltd/mnemion/actions/runs/39315350141) |
| release\.yml | release/4\.24\.0 | success | [Run 39307882234](https://github.com/Perseusxrltd/mnemion/actions/runs/39307882234) |
| release\.yml | release/4\.25\.0 | failure | [Run 39314058004](https://github.com/Perseusxrltd/mnemion/actions/runs/39314058004) |
| release\.yml | release/4\.26\.0 | failure | [Run 39322187837](https://github.com/Perseusxrltd/mnemion/actions/runs/39322187837) |
| verify-artifacts\.yml | main | skipped | [Run 39327941444](https://github.com/Perseusxrltd/mnemion/actions/runs/39327941444) |
| website-release\.yml | v4\.24\.0 | success | [Run 39315345960](https://github.com/Perseusxrltd/mnemion/actions/runs/39315345960) |

## Failed jobs

- [Run 39314058004](https://github.com/Perseusxrltd/mnemion/actions/runs/39314058004): native / ubuntu-22\.04 / x64. Steps: Installed Linux app creates, searches and reopens a real local workspace.
- [Run 39314058004](https://github.com/Perseusxrltd/mnemion/actions/runs/39314058004): native / windows-11-arm / arm64. Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39314058004](https://github.com/Perseusxrltd/mnemion/actions/runs/39314058004): native / macos-15 / arm64. Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39314058004](https://github.com/Perseusxrltd/mnemion/actions/runs/39314058004): native / ubuntu-22\.04-arm / arm64. Steps: Installed Linux app creates, searches and reopens a real local workspace.
- [Run 39314058004](https://github.com/Perseusxrltd/mnemion/actions/runs/39314058004): native / windows-2022 / x64. Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39314058004](https://github.com/Perseusxrltd/mnemion/actions/runs/39314058004): native / macos-15-intel / x64. Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39322187837](https://github.com/Perseusxrltd/mnemion/actions/runs/39322187837): native / ubuntu-22\.04 / x64. Steps: Installed Linux app creates, searches and reopens a real local workspace.
