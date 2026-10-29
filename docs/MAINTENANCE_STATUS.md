# Automated maintenance status

Observed: 2026-10-29T23:50:15+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.55](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.55). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (6)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#47](https://github.com/Perseusxrltd/mnemion/issues/47) | Field report \(4\.46\.40\): multi-agent usage audit — slow/hanging search, suspended connector scope, noisy activity log, unusable vault over MCP, and features left unused | 2026-10-29T15:46:03Z |
| [#48](https://github.com/Perseusxrltd/mnemion/issues/48) | Mnemion as the single system: full replacement of LEDGER/DISPATCH/files, plus vault compatibility | 2026-10-28T09:04:09Z |
| [#49](https://github.com/Perseusxrltd/mnemion/issues/49) | macOS Studio dies at launch: ad-hoc signature rejects Electron Framework | 2026-10-29T15:12:33Z |
| [#50](https://github.com/Perseusxrltd/mnemion/issues/50) | macOS asks for the login keychain password on every Studio secret | 2026-10-29T15:24:22Z |
| [#51](https://github.com/Perseusxrltd/mnemion/issues/51) | Feature: cross-device agent memory continuity and reviewed configuration bundles | 2026-10-29T15:46:04Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40975627713](https://github.com/Perseusxrltd/mnemion/actions/runs/40975627713) |
| public-updates\.yml | v4\.46\.55 | success | [Run 40972439492](https://github.com/Perseusxrltd/mnemion/actions/runs/40972439492) |
| release\.yml | release/4\.46\.55 | success | [Run 40965130140](https://github.com/Perseusxrltd/mnemion/actions/runs/40965130140) |
| verify-artifacts\.yml | main | success | [Run 40971966188](https://github.com/Perseusxrltd/mnemion/actions/runs/40971966188) |
| website-release\.yml | main | success | [Run 40975627673](https://github.com/Perseusxrltd/mnemion/actions/runs/40975627673) |
| website-release\.yml | v4\.46\.55 | success | [Run 40972436052](https://github.com/Perseusxrltd/mnemion/actions/runs/40972436052) |

## Active jobs

[Run 40975627713](https://github.com/Perseusxrltd/mnemion/actions/runs/40975627713): 7/8 jobs completed; 2 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron test.

