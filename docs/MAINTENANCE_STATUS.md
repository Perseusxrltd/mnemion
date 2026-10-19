# Automated maintenance status

Observed: 2026-10-19T13:55:47+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.15.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.15.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds are checked for failed jobs at each observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (10)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#3](https://github.com/Perseusxrltd/mnemion/issues/3) | No built-in remote access option; operators must bring their own reverse proxy / tunnel | 2026-10-11T03:04:30Z |
| [#4](https://github.com/Perseusxrltd/mnemion/issues/4) | No OAuth for hosted agents; static bearer tokens only | 2026-10-10T20:55:33Z |
| [#17](https://github.com/Perseusxrltd/mnemion/issues/17) | Natural-language questions retrieve much worse than keyword queries | 2026-10-19T07:56:12Z |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |
| [#31](https://github.com/Perseusxrltd/mnemion/issues/31) | Recall has no recency signal: older 'open question' memories outrank the newer answer | 2026-10-18T07:47:57Z |
| [#32](https://github.com/Perseusxrltd/mnemion/issues/32) | Feature: encrypted secrets vault, kept apart from searchable memory | 2026-10-19T09:43:02Z |
| [#38](https://github.com/Perseusxrltd/mnemion/issues/38) | Host reset wipes a self-hosted install with no reproducible re-install path or off-host key/state recovery | 2026-10-19T12:13:43Z |
| [#39](https://github.com/Perseusxrltd/mnemion/issues/39) | Buffer memory with automatic additive write-back to Git \(native saves are never pushed upstream\) | 2026-10-19T11:44:25Z |
| [#40](https://github.com/Perseusxrltd/mnemion/issues/40) | Support Grok Build native session/update transcript normalization | 2026-10-19T11:44:19Z |
| [#41](https://github.com/Perseusxrltd/mnemion/issues/41) | Live transcript capture: partial or oversized JSONL suspends the entire source scope | 2026-10-19T11:44:22Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39258552280](https://github.com/Perseusxrltd/mnemion/actions/runs/39258552280) |
| public-updates\.yml | v4\.15\.0 | success | [Run 39251839063](https://github.com/Perseusxrltd/mnemion/actions/runs/39251839063) |
| release\.yml | release/4\.15\.0-r4 | success | [Run 39246219571](https://github.com/Perseusxrltd/mnemion/actions/runs/39246219571) |
| release\.yml | release/4\.16\.0 | failure | [Run 39251058831](https://github.com/Perseusxrltd/mnemion/actions/runs/39251058831) |
| release\.yml | release/4\.17\.0 | in\_progress | [Run 39258607356](https://github.com/Perseusxrltd/mnemion/actions/runs/39258607356) |
| verify-artifacts\.yml | main | skipped | [Run 39257101365](https://github.com/Perseusxrltd/mnemion/actions/runs/39257101365) |
| website-release\.yml | main | success | [Run 39264261319](https://github.com/Perseusxrltd/mnemion/actions/runs/39264261319) |
| website-release\.yml | v4\.15\.0 | success | [Run 39251835481](https://github.com/Perseusxrltd/mnemion/actions/runs/39251835481) |

## Failed jobs

- [Run 39251058831](https://github.com/Perseusxrltd/mnemion/actions/runs/39251058831): native / macos-15 / arm64. Steps: Installed app creates, searches and reopens a real local workspace.
