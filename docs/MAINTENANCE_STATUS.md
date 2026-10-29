# Automated maintenance status

Observed: 2026-10-29T20:36:55+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.52](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.52). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | success | [Run 40934940700](https://github.com/Perseusxrltd/mnemion/actions/runs/40934940700) |
| database-cache\.yml | main | success | [Run 40861058907](https://github.com/Perseusxrltd/mnemion/actions/runs/40861058907) |
| public-updates\.yml | v4\.46\.52 | success | [Run 40853494264](https://github.com/Perseusxrltd/mnemion/actions/runs/40853494264) |
| release\.yml | release/4\.46\.52 | success | [Run 40844389559](https://github.com/Perseusxrltd/mnemion/actions/runs/40844389559) |
| release\.yml | release/4\.46\.53 | failure | [Run 40896509541](https://github.com/Perseusxrltd/mnemion/actions/runs/40896509541) |
| release\.yml | release/4\.46\.54 | success | [Run 40941892068](https://github.com/Perseusxrltd/mnemion/actions/runs/40941892068) |
| verify-artifacts\.yml | main | in\_progress | [Run 40950510945](https://github.com/Perseusxrltd/mnemion/actions/runs/40950510945) |
| website-release\.yml | main | success | [Run 40934940622](https://github.com/Perseusxrltd/mnemion/actions/runs/40934940622) |
| website-release\.yml | v4\.46\.52 | success | [Run 40853490883](https://github.com/Perseusxrltd/mnemion/actions/runs/40853490883) |

## Active jobs

[Run 40950510945](https://github.com/Perseusxrltd/mnemion/actions/runs/40950510945): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.


## Unsuccessful jobs

- [Run 40896509541](https://github.com/Perseusxrltd/mnemion/actions/runs/40896509541): native / macos-26 / arm64 (failure). Steps: Verify model custody with real native child processes, Retain generated desktop-content secret scan receipt.
