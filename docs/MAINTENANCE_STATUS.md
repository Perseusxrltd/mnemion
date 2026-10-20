# Automated maintenance status

Observed: 2026-10-20T01:11:45+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.28.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.28.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds are checked for failed jobs at each observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#3](https://github.com/Perseusxrltd/mnemion/issues/3) | No built-in remote access option; operators must bring their own reverse proxy / tunnel | 2026-10-11T03:04:30Z |
| [#4](https://github.com/Perseusxrltd/mnemion/issues/4) | No OAuth for hosted agents; static bearer tokens only | 2026-10-10T20:55:33Z |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39351890145](https://github.com/Perseusxrltd/mnemion/actions/runs/39351890145) |
| public-updates\.yml | v4\.28\.0 | success | [Run 39340780959](https://github.com/Perseusxrltd/mnemion/actions/runs/39340780959) |
| release\.yml | release/4\.28\.0 | success | [Run 39333925246](https://github.com/Perseusxrltd/mnemion/actions/runs/39333925246) |
| release\.yml | release/4\.29\.0 | success | [Run 39347302345](https://github.com/Perseusxrltd/mnemion/actions/runs/39347302345) |
| release\.yml | release/4\.30\.0 | queued | [Run 39352016357](https://github.com/Perseusxrltd/mnemion/actions/runs/39352016357) |
| verify-artifacts\.yml | main | in\_progress | [Run 39352013400](https://github.com/Perseusxrltd/mnemion/actions/runs/39352013400) |
| website-release\.yml | v4\.28\.0 | success | [Run 39340777988](https://github.com/Perseusxrltd/mnemion/actions/runs/39340777988) |
