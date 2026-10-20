# Automated maintenance status

Observed: 2026-10-20T08:00:53+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.33.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.33.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39388058383](https://github.com/Perseusxrltd/mnemion/actions/runs/39388058383) |
| public-updates\.yml | v4\.33\.0 | success | [Run 39387468667](https://github.com/Perseusxrltd/mnemion/actions/runs/39387468667) |
| release\.yml | release/4\.33\.0 | success | [Run 39382743155](https://github.com/Perseusxrltd/mnemion/actions/runs/39382743155) |
| release\.yml | release/4\.34\.0 | in\_progress | [Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080) |
| verify-artifacts\.yml | main | success | [Run 39387307827](https://github.com/Perseusxrltd/mnemion/actions/runs/39387307827) |
| website-release\.yml | v4\.33\.0 | success | [Run 39387465064](https://github.com/Perseusxrltd/mnemion/actions/runs/39387465064) |

## Active jobs

[Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080): 26/31 jobs completed; 26 succeeded.

- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15 / arm64: in\_progress — Packaged Mac update, restart guards and relaunch.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-2022 / x64: in\_progress — Native Windows installation, authenticated upgrade and relaunch.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.

