# Automated maintenance status

Observed: 2026-10-29T07:49:18+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.49](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.49). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | in\_progress | [Run 40837798626](https://github.com/Perseusxrltd/mnemion/actions/runs/40837798626) |
| public-updates\.yml | v4\.46\.49 | success | [Run 40820128156](https://github.com/Perseusxrltd/mnemion/actions/runs/40820128156) |
| release\.yml | release/4\.46\.49 | success | [Run 40812422400](https://github.com/Perseusxrltd/mnemion/actions/runs/40812422400) |
| release\.yml | release/4\.46\.50 | failure | [Run 40815491489](https://github.com/Perseusxrltd/mnemion/actions/runs/40815491489) |
| release\.yml | release/4\.46\.51 | failure | [Run 40829255129](https://github.com/Perseusxrltd/mnemion/actions/runs/40829255129) |
| release\.yml | release/4\.46\.51-r2 | in\_progress | [Run 40835999398](https://github.com/Perseusxrltd/mnemion/actions/runs/40835999398) |
| verify-artifacts\.yml | main | skipped | [Run 40835184620](https://github.com/Perseusxrltd/mnemion/actions/runs/40835184620) |
| website-release\.yml | main | success | [Run 40837798631](https://github.com/Perseusxrltd/mnemion/actions/runs/40837798631) |
| website-release\.yml | v4\.46\.49 | success | [Run 40820125119](https://github.com/Perseusxrltd/mnemion/actions/runs/40820125119) |

## Active jobs

[Run 40837798626](https://github.com/Perseusxrltd/mnemion/actions/runs/40837798626): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/frontend run test:telemetry.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.12\): in\_progress — Run uv sync --locked --python 3\.12 --group dev.
- supervision \(macos-26\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.13\): in\_progress — Run uv sync --locked --python 3\.13 --group dev.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.

[Run 40835999398](https://github.com/Perseusxrltd/mnemion/actions/runs/40835999398): 15/21 jobs completed; 14 succeeded.

- native / ubuntu-22\.04-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-11-arm / arm64: in\_progress — Select the service interpreter independently of the desktop client.
- native / ubuntu-22\.04 / x64: in\_progress — Run npm --prefix studio/electron test.
- native / macos-26 / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / macos-15-intel / x64: in\_progress — Locked native service build dependencies.
- native / windows-2022 / x64: in\_progress — Run npm --prefix studio/electron test.


## Unsuccessful jobs

- [Run 40815491489](https://github.com/Perseusxrltd/mnemion/actions/runs/40815491489): native / ubuntu-22\.04 / x64 (failure). Steps: Installed Linux app creates, searches and reopens a real local workspace.
- [Run 40829255129](https://github.com/Perseusxrltd/mnemion/actions/runs/40829255129): native / windows-2022 / x64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40829255129](https://github.com/Perseusxrltd/mnemion/actions/runs/40829255129): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
