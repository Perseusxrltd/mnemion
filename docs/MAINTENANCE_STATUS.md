# Automated maintenance status

Observed: 2026-10-28T23:42:22+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.44](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.44). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#47](https://github.com/Perseusxrltd/mnemion/issues/47) | Field report \(4\.46\.40\): multi-agent usage audit — slow/hanging search, suspended connector scope, noisy activity log, unusable vault over MCP, and features left unused | 2026-10-28T17:01:24Z |
| [#48](https://github.com/Perseusxrltd/mnemion/issues/48) | Mnemion as the single system: full replacement of LEDGER/DISPATCH/files, plus vault compatibility | 2026-10-28T09:04:09Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | failure | [Run 40786527751](https://github.com/Perseusxrltd/mnemion/actions/runs/40786527751) |
| public-updates\.yml | v4\.46\.44 | failure | [Run 40702705371](https://github.com/Perseusxrltd/mnemion/actions/runs/40702705371) |
| release\.yml | release/4\.46\.44 | success | [Run 40690852078](https://github.com/Perseusxrltd/mnemion/actions/runs/40690852078) |
| release\.yml | release/4\.46\.45 | failure | [Run 40695913724](https://github.com/Perseusxrltd/mnemion/actions/runs/40695913724) |
| release\.yml | release/4\.46\.46 | failure | [Run 40757944923](https://github.com/Perseusxrltd/mnemion/actions/runs/40757944923) |
| verify-artifacts\.yml | main | skipped | [Run 40768286929](https://github.com/Perseusxrltd/mnemion/actions/runs/40768286929) |
| website-release\.yml | main | success | [Run 40786527984](https://github.com/Perseusxrltd/mnemion/actions/runs/40786527984) |
| website-release\.yml | v4\.46\.44 | success | [Run 40702700363](https://github.com/Perseusxrltd/mnemion/actions/runs/40702700363) |

## Unsuccessful jobs

- [Run 40786527751](https://github.com/Perseusxrltd/mnemion/actions/runs/40786527751): studio (failure). Steps: Check the lightweight native client before six-platform packaging.
- [Run 40702705371](https://github.com/Perseusxrltd/mnemion/actions/runs/40702705371): macos / arm64 public upgrade (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40695913724](https://github.com/Perseusxrltd/mnemion/actions/runs/40695913724): native / macos-26 / arm64 (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40757944923](https://github.com/Perseusxrltd/mnemion/actions/runs/40757944923): native / windows-2022 / x64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40757944923](https://github.com/Perseusxrltd/mnemion/actions/runs/40757944923): native / macos-15-intel / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
