# Automated maintenance status

Observed: 2026-10-14T13:59:04+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.2.4](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.2.4). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds are checked for failed jobs at each observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (6)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#3](https://github.com/Perseusxrltd/mnemion/issues/3) | No built-in remote access option; operators must bring their own reverse proxy / tunnel | 2026-10-11T03:04:30Z |
| [#4](https://github.com/Perseusxrltd/mnemion/issues/4) | No OAuth for hosted agents; static bearer tokens only | 2026-10-10T20:55:33Z |
| [#13](https://github.com/Perseusxrltd/mnemion/issues/13) | Worker idles at ~1\.6 GB RSS and API at ~0\.8 GB: models loaded twice, hard on small hosts | 2026-10-13T12:03:25Z |
| [#17](https://github.com/Perseusxrltd/mnemion/issues/17) | Natural-language questions retrieve much worse than keyword queries | 2026-10-13T20:00:14Z |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |
| [#32](https://github.com/Perseusxrltd/mnemion/issues/32) | Feature: encrypted secrets vault, kept apart from searchable memory | 2026-10-13T05:57:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 38574693922](https://github.com/Perseusxrltd/mnemion/actions/runs/38574693922) |
| public-updates\.yml | v4\.2\.4 | success | [Run 38563825863](https://github.com/Perseusxrltd/mnemion/actions/runs/38563825863) |
| release\.yml | release/4\.2\.4 | success | [Run 38559090340](https://github.com/Perseusxrltd/mnemion/actions/runs/38559090340) |
| release\.yml | release/4\.2\.5 | failure | [Run 38563469356](https://github.com/Perseusxrltd/mnemion/actions/runs/38563469356) |
| release\.yml | release/4\.2\.5-r2 | success | [Run 38571557139](https://github.com/Perseusxrltd/mnemion/actions/runs/38571557139) |
| verify-artifacts\.yml | main | in\_progress | [Run 38576410392](https://github.com/Perseusxrltd/mnemion/actions/runs/38576410392) |
| website-release\.yml | v4\.2\.4 | success | [Run 38563821954](https://github.com/Perseusxrltd/mnemion/actions/runs/38563821954) |

## Failed jobs

- [Run 38563469356](https://github.com/Perseusxrltd/mnemion/actions/runs/38563469356): checks / supervision \(macos-15\). Steps: Verify managed installation, signed updates and rollback with real processes.
- [Run 38563469356](https://github.com/Perseusxrltd/mnemion/actions/runs/38563469356): checks / supervision \(macos-15-intel\). Steps: Verify managed installation, signed updates and rollback with real processes.
- [Run 38563469356](https://github.com/Perseusxrltd/mnemion/actions/runs/38563469356): native / windows-2022 / x64. Steps: Native Windows installation, authenticated upgrade and relaunch.
