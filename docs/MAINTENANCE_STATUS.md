# Automated maintenance status

Observed: 2026-10-31T20:11:23+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.62](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.62). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | in\_progress | [Run 41237650725](https://github.com/Perseusxrltd/mnemion/actions/runs/41237650725) |
| public-updates\.yml | v4\.46\.62 | success | [Run 41201338411](https://github.com/Perseusxrltd/mnemion/actions/runs/41201338411) |
| release\.yml | release/4\.46\.62 | success | [Run 41196826469](https://github.com/Perseusxrltd/mnemion/actions/runs/41196826469) |
| verify-artifacts\.yml | main | success | [Run 41200981019](https://github.com/Perseusxrltd/mnemion/actions/runs/41200981019) |
| website-release\.yml | main | success | [Run 41203708660](https://github.com/Perseusxrltd/mnemion/actions/runs/41203708660) |
| website-release\.yml | v4\.46\.62 | success | [Run 41201336239](https://github.com/Perseusxrltd/mnemion/actions/runs/41201336239) |

## Active jobs

[Run 41237650725](https://github.com/Perseusxrltd/mnemion/actions/runs/41237650725): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.13\): in\_progress — Run python -m pip install uv==0\.12\.24.
- supervision \(macos-26\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.14\): in\_progress — Run python -m pip install uv==0\.12\.24.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.

