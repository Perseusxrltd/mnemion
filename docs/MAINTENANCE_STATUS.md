# Automated maintenance status

Observed: 2026-10-15T04:22:06+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.4.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.4.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds are checked for failed jobs at each observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (6)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#3](https://github.com/Perseusxrltd/mnemion/issues/3) | No built-in remote access option; operators must bring their own reverse proxy / tunnel | 2026-10-11T03:04:30Z |
| [#4](https://github.com/Perseusxrltd/mnemion/issues/4) | No OAuth for hosted agents; static bearer tokens only | 2026-10-10T20:55:33Z |
| [#17](https://github.com/Perseusxrltd/mnemion/issues/17) | Natural-language questions retrieve much worse than keyword queries | 2026-10-13T20:00:14Z |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |
| [#31](https://github.com/Perseusxrltd/mnemion/issues/31) | Recall has no recency signal: older 'open question' memories outrank the newer answer | 2026-10-14T19:51:04Z |
| [#32](https://github.com/Perseusxrltd/mnemion/issues/32) | Feature: encrypted secrets vault, kept apart from searchable memory | 2026-10-13T05:57:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 38679996018](https://github.com/Perseusxrltd/mnemion/actions/runs/38679996018) |
| public-updates\.yml | v4\.4\.0 | success | [Run 38655462084](https://github.com/Perseusxrltd/mnemion/actions/runs/38655462084) |
| release\.yml | release/4\.4\.0 | success | [Run 38651001133](https://github.com/Perseusxrltd/mnemion/actions/runs/38651001133) |
| release\.yml | release/4\.5\.0 | failure | [Run 38669057276](https://github.com/Perseusxrltd/mnemion/actions/runs/38669057276) |
| release\.yml | release/4\.5\.0-r2 | failure | [Run 38674242209](https://github.com/Perseusxrltd/mnemion/actions/runs/38674242209) |
| release\.yml | release/4\.6\.0 | cancelled | [Run 38675510809](https://github.com/Perseusxrltd/mnemion/actions/runs/38675510809) |
| release\.yml | release/4\.6\.0-r2 | cancelled | [Run 38677594445](https://github.com/Perseusxrltd/mnemion/actions/runs/38677594445) |
| release\.yml | release/4\.6\.0-r3 | queued | [Run 38680133894](https://github.com/Perseusxrltd/mnemion/actions/runs/38680133894) |
| verify-artifacts\.yml | main | skipped | [Run 38681059715](https://github.com/Perseusxrltd/mnemion/actions/runs/38681059715) |
| website-release\.yml | v4\.4\.0 | success | [Run 38655459186](https://github.com/Perseusxrltd/mnemion/actions/runs/38655459186) |

## Failed jobs

- [Run 38669057276](https://github.com/Perseusxrltd/mnemion/actions/runs/38669057276): native / windows-11-arm / arm64. Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 38669057276](https://github.com/Perseusxrltd/mnemion/actions/runs/38669057276): native / windows-2022 / x64. Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 38674242209](https://github.com/Perseusxrltd/mnemion/actions/runs/38674242209): native / windows-2022 / x64. Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 38674242209](https://github.com/Perseusxrltd/mnemion/actions/runs/38674242209): native / windows-11-arm / arm64. Steps: Installed app creates, searches and reopens a real local workspace.
