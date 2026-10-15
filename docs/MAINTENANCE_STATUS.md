# Automated maintenance status

Observed: 2026-10-15T09:33:26+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.7.1](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.7.1). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds are checked for failed jobs at each observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (6)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#3](https://github.com/Perseusxrltd/mnemion/issues/3) | No built-in remote access option; operators must bring their own reverse proxy / tunnel | 2026-10-11T03:04:30Z |
| [#4](https://github.com/Perseusxrltd/mnemion/issues/4) | No OAuth for hosted agents; static bearer tokens only | 2026-10-10T20:55:33Z |
| [#17](https://github.com/Perseusxrltd/mnemion/issues/17) | Natural-language questions retrieve much worse than keyword queries | 2026-10-13T20:00:14Z |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |
| [#31](https://github.com/Perseusxrltd/mnemion/issues/31) | Recall has no recency signal: older 'open question' memories outrank the newer answer | 2026-10-15T07:55:51Z |
| [#32](https://github.com/Perseusxrltd/mnemion/issues/32) | Feature: encrypted secrets vault, kept apart from searchable memory | 2026-10-13T05:57:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 38713690998](https://github.com/Perseusxrltd/mnemion/actions/runs/38713690998) |
| public-updates\.yml | v4\.7\.1 | success | [Run 38690301500](https://github.com/Perseusxrltd/mnemion/actions/runs/38690301500) |
| release\.yml | release/4\.7\.1 | success | [Run 38686774445](https://github.com/Perseusxrltd/mnemion/actions/runs/38686774445) |
| release\.yml | release/4\.8\.0 | cancelled | [Run 38711982415](https://github.com/Perseusxrltd/mnemion/actions/runs/38711982415) |
| release\.yml | release/4\.8\.0-r2 | queued | [Run 38713709815](https://github.com/Perseusxrltd/mnemion/actions/runs/38713709815) |
| verify-artifacts\.yml | main | skipped | [Run 38712418377](https://github.com/Perseusxrltd/mnemion/actions/runs/38712418377) |
| website-release\.yml | v4\.7\.1 | success | [Run 38690298719](https://github.com/Perseusxrltd/mnemion/actions/runs/38690298719) |

## Failed jobs

- [Run 38713690998](https://github.com/Perseusxrltd/mnemion/actions/runs/38713690998): container \(ubuntu-22\.04\). Steps: Build the actual deployment image with its documentation.
- [Run 38713709815](https://github.com/Perseusxrltd/mnemion/actions/runs/38713709815): checks / container \(ubuntu-22\.04-arm\). Steps: Build the actual deployment image with its documentation.
- [Run 38713709815](https://github.com/Perseusxrltd/mnemion/actions/runs/38713709815): checks / container \(ubuntu-22\.04\). Steps: Build the actual deployment image with its documentation.
