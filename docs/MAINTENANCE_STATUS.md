# Automated maintenance status

Observed: 2026-11-02T21:56:47+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.65](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.65). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | success | [Run 41406607799](https://github.com/Perseusxrltd/mnemion/actions/runs/41406607799) |
| database-cache\.yml | main | success | [Run 41444342454](https://github.com/Perseusxrltd/mnemion/actions/runs/41444342454) |
| public-updates\.yml | v4\.46\.65 | failure | [Run 41374873484](https://github.com/Perseusxrltd/mnemion/actions/runs/41374873484) |
| release\.yml | release/4\.46\.65 | success | [Run 41369730714](https://github.com/Perseusxrltd/mnemion/actions/runs/41369730714) |
| verify-artifacts\.yml | main | success | [Run 41374503130](https://github.com/Perseusxrltd/mnemion/actions/runs/41374503130) |
| website-release\.yml | main | success | [Run 41532695913](https://github.com/Perseusxrltd/mnemion/actions/runs/41532695913) |
| website-release\.yml | v4\.46\.65 | success | [Run 41374870627](https://github.com/Perseusxrltd/mnemion/actions/runs/41374870627) |

## Unsuccessful jobs

- [Run 41374873484](https://github.com/Perseusxrltd/mnemion/actions/runs/41374873484): linux / arm64 public upgrade (failure). Steps: Install public release and observe its automatic update.
