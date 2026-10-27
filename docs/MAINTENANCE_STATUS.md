# Automated maintenance status

Observed: 2026-10-27T14:40:46+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.39](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.39). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40517759157](https://github.com/Perseusxrltd/mnemion/actions/runs/40517759157) |
| public-updates\.yml | v4\.46\.39 | success | [Run 40521216857](https://github.com/Perseusxrltd/mnemion/actions/runs/40521216857) |
| release\.yml | release/4\.46\.39 | success | [Run 40504681891](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891) |
| release\.yml | release/4\.46\.40 | in\_progress | [Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119) |
| verify-artifacts\.yml | main | success | [Run 40512666290](https://github.com/Perseusxrltd/mnemion/actions/runs/40512666290) |
| website-release\.yml | main | success | [Run 40501408889](https://github.com/Perseusxrltd/mnemion/actions/runs/40501408889) |
| website-release\.yml | v4\.46\.39 | in\_progress | [Run 40521210268](https://github.com/Perseusxrltd/mnemion/actions/runs/40521210268) |

## Active jobs

[Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119): 18/21 jobs completed; 17 succeeded.

- native / macos-15-intel / x64: in\_progress — Sign and verify the free macOS update archive.
- native / windows-2022 / x64: in\_progress — Native Windows installation, authenticated upgrade and relaunch.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

