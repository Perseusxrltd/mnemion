# Automated maintenance status

Observed: 2026-10-29T15:52:26+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | queued | [Run 40905758692](https://github.com/Perseusxrltd/mnemion/actions/runs/40905758692) |
| database-cache\.yml | main | success | [Run 40861058907](https://github.com/Perseusxrltd/mnemion/actions/runs/40861058907) |
| public-updates\.yml | v4\.46\.52 | success | [Run 40853494264](https://github.com/Perseusxrltd/mnemion/actions/runs/40853494264) |
| release\.yml | release/4\.46\.52 | success | [Run 40844389559](https://github.com/Perseusxrltd/mnemion/actions/runs/40844389559) |
| release\.yml | release/4\.46\.53 | in\_progress | [Run 40896509541](https://github.com/Perseusxrltd/mnemion/actions/runs/40896509541) |
| verify-artifacts\.yml | main | success | [Run 40852860198](https://github.com/Perseusxrltd/mnemion/actions/runs/40852860198) |
| website-release\.yml | main | success | [Run 40905758771](https://github.com/Perseusxrltd/mnemion/actions/runs/40905758771) |
| website-release\.yml | v4\.46\.52 | success | [Run 40853490883](https://github.com/Perseusxrltd/mnemion/actions/runs/40853490883) |

## Active jobs

[Run 40905758692](https://github.com/Perseusxrltd/mnemion/actions/runs/40905758692): 4/12 jobs completed; 4 succeeded.

- studio: in\_progress — Verify wheel and source package include the matching web Studio.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04\): in\_progress — Post Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-26\): queued.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40896509541](https://github.com/Perseusxrltd/mnemion/actions/runs/40896509541): 20/21 jobs completed; 18 succeeded.

- native / windows-11-arm / arm64: in\_progress.


## Unsuccessful jobs

- [Run 40896509541](https://github.com/Perseusxrltd/mnemion/actions/runs/40896509541): native / macos-26 / arm64 (failure). Steps: Verify model custody with real native child processes, Retain generated desktop-content secret scan receipt.
