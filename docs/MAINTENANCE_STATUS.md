# Automated maintenance status

Observed: 2026-10-20T12:05:54+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.37.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.37.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T11:54:56Z |
| [#46](https://github.com/Perseusxrltd/mnemion/issues/46) | Deployment access: Codex/Astra cannot see the existing office task and memory spaces | 2026-10-20T12:05:17Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 39419696237](https://github.com/Perseusxrltd/mnemion/actions/runs/39419696237) |
| public-updates\.yml | v4\.37\.0 | success | [Run 39403004762](https://github.com/Perseusxrltd/mnemion/actions/runs/39403004762) |
| release\.yml | release/4\.37\.0 | success | [Run 39397479332](https://github.com/Perseusxrltd/mnemion/actions/runs/39397479332) |
| release\.yml | release/4\.38\.0 | in\_progress | [Run 39416800968](https://github.com/Perseusxrltd/mnemion/actions/runs/39416800968) |
| verify-artifacts\.yml | main | success | [Run 39402826454](https://github.com/Perseusxrltd/mnemion/actions/runs/39402826454) |
| website-release\.yml | v4\.37\.0 | success | [Run 39403000169](https://github.com/Perseusxrltd/mnemion/actions/runs/39403000169) |

## Active jobs

[Run 39419696237](https://github.com/Perseusxrltd/mnemion/actions/runs/39419696237): 0/3 jobs completed; 0 succeeded.

- Select checks: queued.
- studio: queued.
- lint: queued.

[Run 39416800968](https://github.com/Perseusxrltd/mnemion/actions/runs/39416800968): 28/31 jobs completed; 26 succeeded.

- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-2022 / x64: in\_progress — Native Windows installation, authenticated upgrade and relaunch.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Failed jobs

- [Run 39416800968](https://github.com/Perseusxrltd/mnemion/actions/runs/39416800968): checks / container \(ubuntu-22\.04\). Steps: Build the actual deployment image with its documentation.
- [Run 39416800968](https://github.com/Perseusxrltd/mnemion/actions/runs/39416800968): checks / container \(ubuntu-22\.04-arm\). Steps: Build the actual deployment image with its documentation.
