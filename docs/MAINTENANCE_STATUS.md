# Automated maintenance status

Observed: 2026-10-29T01:52:39+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.46](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.46). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | in\_progress | [Run 40802929823](https://github.com/Perseusxrltd/mnemion/actions/runs/40802929823) |
| public-updates\.yml | v4\.46\.46 | success | [Run 40801713765](https://github.com/Perseusxrltd/mnemion/actions/runs/40801713765) |
| release\.yml | release/4\.46\.46-r2 | success | [Run 40793646583](https://github.com/Perseusxrltd/mnemion/actions/runs/40793646583) |
| release\.yml | release/4\.46\.47 | in\_progress | [Run 40801649181](https://github.com/Perseusxrltd/mnemion/actions/runs/40801649181) |
| verify-artifacts\.yml | main | success | [Run 40801321439](https://github.com/Perseusxrltd/mnemion/actions/runs/40801321439) |
| website-release\.yml | main | success | [Run 40802930121](https://github.com/Perseusxrltd/mnemion/actions/runs/40802930121) |
| website-release\.yml | v4\.46\.46 | success | [Run 40801711006](https://github.com/Perseusxrltd/mnemion/actions/runs/40801711006) |

## Active jobs

[Run 40802929823](https://github.com/Perseusxrltd/mnemion/actions/runs/40802929823): 5/12 jobs completed; 5 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron test.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-26\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40801649181](https://github.com/Perseusxrltd/mnemion/actions/runs/40801649181): 15/21 jobs completed; 14 succeeded.

- native / ubuntu-22\.04 / x64: in\_progress — Run npm --prefix packages/client ci.
- native / macos-26 / arm64: in\_progress — Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
- native / windows-2022 / x64: in\_progress — Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
- native / windows-11-arm / arm64: in\_progress — Select the service interpreter independently of the desktop client.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Run npm --prefix studio/electron ci.
- native / macos-15-intel / x64: in\_progress — Locked native service build dependencies.

