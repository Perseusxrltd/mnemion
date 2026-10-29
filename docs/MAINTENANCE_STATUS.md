# Automated maintenance status

Observed: 2026-10-29T09:57:33+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.52](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.52). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (4)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#47](https://github.com/Perseusxrltd/mnemion/issues/47) | Field report \(4\.46\.40\): multi-agent usage audit — slow/hanging search, suspended connector scope, noisy activity log, unusable vault over MCP, and features left unused | 2026-10-28T17:01:24Z |
| [#48](https://github.com/Perseusxrltd/mnemion/issues/48) | Mnemion as the single system: full replacement of LEDGER/DISPATCH/files, plus vault compatibility | 2026-10-28T09:04:09Z |
| [#49](https://github.com/Perseusxrltd/mnemion/issues/49) | macOS Studio dies at launch: ad-hoc signature rejects Electron Framework | 2026-10-29T08:53:25Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40853583995](https://github.com/Perseusxrltd/mnemion/actions/runs/40853583995) |
| public-updates\.yml | v4\.46\.52 | in\_progress | [Run 40853494264](https://github.com/Perseusxrltd/mnemion/actions/runs/40853494264) |
| release\.yml | release/4\.46\.52 | success | [Run 40844389559](https://github.com/Perseusxrltd/mnemion/actions/runs/40844389559) |
| verify-artifacts\.yml | main | success | [Run 40852860198](https://github.com/Perseusxrltd/mnemion/actions/runs/40852860198) |
| website-release\.yml | main | success | [Run 40853584019](https://github.com/Perseusxrltd/mnemion/actions/runs/40853584019) |
| website-release\.yml | v4\.46\.52 | success | [Run 40853490883](https://github.com/Perseusxrltd/mnemion/actions/runs/40853490883) |

## Active jobs

[Run 40853583995](https://github.com/Perseusxrltd/mnemion/actions/runs/40853583995): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron ci.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-26\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.

[Run 40853494264](https://github.com/Perseusxrltd/mnemion/actions/runs/40853494264): 1/7 jobs completed; 1 succeeded.

- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.

