# Automated maintenance status

Observed: 2026-10-14T11:50:16+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.2.3](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.2.3). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. A failed job is inspected once per changed attempt; this automation never retries a build or publishes a release.

## Open issues (7)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#3](https://github.com/Perseusxrltd/mnemion/issues/3) | No built-in remote access option; operators must bring their own reverse proxy / tunnel | 2026-10-11T03:04:30Z |
| [#4](https://github.com/Perseusxrltd/mnemion/issues/4) | No OAuth for hosted agents; static bearer tokens only | 2026-10-10T20:55:33Z |
| [#13](https://github.com/Perseusxrltd/mnemion/issues/13) | Worker idles at ~1\.6 GB RSS and API at ~0\.8 GB: models loaded twice, hard on small hosts | 2026-10-13T12:03:25Z |
| [#17](https://github.com/Perseusxrltd/mnemion/issues/17) | Natural-language questions retrieve much worse than keyword queries | 2026-10-13T20:00:14Z |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |
| [#32](https://github.com/Perseusxrltd/mnemion/issues/32) | Feature: encrypted secrets vault, kept apart from searchable memory | 2026-10-13T05:57:12Z |
| [#36](https://github.com/Perseusxrltd/mnemion/issues/36) | Managed host on 4\.1\.x can't reach 4\.2\.x: no guided schema upgrade, and status doesn't show the blocked update | 2026-10-14T11:50:00Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 38559073557](https://github.com/Perseusxrltd/mnemion/actions/runs/38559073557) |
| public-updates\.yml | v4\.2\.3 | success | [Run 38436415685](https://github.com/Perseusxrltd/mnemion/actions/runs/38436415685) |
| release\.yml | release/4\.2\.3-r2 | success | [Run 38432717233](https://github.com/Perseusxrltd/mnemion/actions/runs/38432717233) |
| release\.yml | release/4\.2\.4 | in\_progress | [Run 38559090340](https://github.com/Perseusxrltd/mnemion/actions/runs/38559090340) |
| verify-artifacts\.yml | main | success | [Run 38436199163](https://github.com/Perseusxrltd/mnemion/actions/runs/38436199163) |
| website-release\.yml | main | success | [Run 38516147515](https://github.com/Perseusxrltd/mnemion/actions/runs/38516147515) |
| website-release\.yml | v4\.2\.3 | success | [Run 38436410364](https://github.com/Perseusxrltd/mnemion/actions/runs/38436410364) |
