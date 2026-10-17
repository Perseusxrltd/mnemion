# Automated maintenance status

Observed: 2026-10-17T09:57:24+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.11.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.11.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds are checked for failed jobs at each observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (8)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#3](https://github.com/Perseusxrltd/mnemion/issues/3) | No built-in remote access option; operators must bring their own reverse proxy / tunnel | 2026-10-11T03:04:30Z |
| [#4](https://github.com/Perseusxrltd/mnemion/issues/4) | No OAuth for hosted agents; static bearer tokens only | 2026-10-10T20:55:33Z |
| [#17](https://github.com/Perseusxrltd/mnemion/issues/17) | Natural-language questions retrieve much worse than keyword queries | 2026-10-13T20:00:14Z |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |
| [#31](https://github.com/Perseusxrltd/mnemion/issues/31) | Recall has no recency signal: older 'open question' memories outrank the newer answer | 2026-10-17T07:56:35Z |
| [#32](https://github.com/Perseusxrltd/mnemion/issues/32) | Feature: encrypted secrets vault, kept apart from searchable memory | 2026-10-13T05:57:12Z |
| [#38](https://github.com/Perseusxrltd/mnemion/issues/38) | Host reset wipes a self-hosted install with no reproducible re-install path or off-host key/state recovery | 2026-10-17T09:57:06Z |
| [#39](https://github.com/Perseusxrltd/mnemion/issues/39) | Buffer memory with automatic additive write-back to Git \(native saves are never pushed upstream\) | 2026-10-17T09:57:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 38755654205](https://github.com/Perseusxrltd/mnemion/actions/runs/38755654205) |
| public-updates\.yml | v4\.11\.0 | success | [Run 38762930423](https://github.com/Perseusxrltd/mnemion/actions/runs/38762930423) |
| release\.yml | release/4\.11\.0 | success | [Run 38755751232](https://github.com/Perseusxrltd/mnemion/actions/runs/38755751232) |
| verify-artifacts\.yml | main | success | [Run 38762688790](https://github.com/Perseusxrltd/mnemion/actions/runs/38762688790) |
| website-release\.yml | main | success | [Run 39004489229](https://github.com/Perseusxrltd/mnemion/actions/runs/39004489229) |
| website-release\.yml | v4\.11\.0 | success | [Run 38762926335](https://github.com/Perseusxrltd/mnemion/actions/runs/38762926335) |
