# Automated maintenance status

Observed: 2026-11-01T22:24:09+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.63](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.63). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | in\_progress | [Run 41355948958](https://github.com/Perseusxrltd/mnemion/actions/runs/41355948958) |
| public-updates\.yml | v4\.46\.63 | success | [Run 41354406946](https://github.com/Perseusxrltd/mnemion/actions/runs/41354406946) |
| release\.yml | release/4\.46\.63 | success | [Run 41349211852](https://github.com/Perseusxrltd/mnemion/actions/runs/41349211852) |
| release\.yml | release/4\.46\.64 | in\_progress | [Run 41355830658](https://github.com/Perseusxrltd/mnemion/actions/runs/41355830658) |
| verify-artifacts\.yml | main | success | [Run 41353986084](https://github.com/Perseusxrltd/mnemion/actions/runs/41353986084) |
| website-release\.yml | main | success | [Run 41356870595](https://github.com/Perseusxrltd/mnemion/actions/runs/41356870595) |
| website-release\.yml | v4\.46\.63 | success | [Run 41354404727](https://github.com/Perseusxrltd/mnemion/actions/runs/41354404727) |

## Active jobs

[Run 41355948958](https://github.com/Perseusxrltd/mnemion/actions/runs/41355948958): 8/12 jobs completed; 8 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.

[Run 41355830658](https://github.com/Perseusxrltd/mnemion/actions/runs/41355830658): 15/21 jobs completed; 14 succeeded.

- native / ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Run npm --prefix studio/electron test.
- native / macos-26 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.

