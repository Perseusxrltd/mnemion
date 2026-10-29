# Automated maintenance status

Observed: 2026-10-29T02:50:19+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.47](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.47). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | in\_progress | [Run 40808620574](https://github.com/Perseusxrltd/mnemion/actions/runs/40808620574) |
| public-updates\.yml | v4\.46\.47 | in\_progress | [Run 40808263819](https://github.com/Perseusxrltd/mnemion/actions/runs/40808263819) |
| release\.yml | release/4\.46\.47 | success | [Run 40801649181](https://github.com/Perseusxrltd/mnemion/actions/runs/40801649181) |
| release\.yml | release/4\.46\.48 | in\_progress | [Run 40806507811](https://github.com/Perseusxrltd/mnemion/actions/runs/40806507811) |
| verify-artifacts\.yml | main | success | [Run 40807818311](https://github.com/Perseusxrltd/mnemion/actions/runs/40807818311) |
| website-release\.yml | main | success | [Run 40808620485](https://github.com/Perseusxrltd/mnemion/actions/runs/40808620485) |
| website-release\.yml | v4\.46\.47 | success | [Run 40808260569](https://github.com/Perseusxrltd/mnemion/actions/runs/40808260569) |

## Active jobs

[Run 40808620574](https://github.com/Perseusxrltd/mnemion/actions/runs/40808620574): 4/12 jobs completed; 4 succeeded.

- studio: in\_progress — Run npm --prefix studio/frontend run test:telemetry.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-26\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40808263819](https://github.com/Perseusxrltd/mnemion/actions/runs/40808263819): 1/7 jobs completed; 1 succeeded.

- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 40806507811](https://github.com/Perseusxrltd/mnemion/actions/runs/40806507811): 13/14 jobs completed; 12 succeeded.

- native / native\_database / Database / windows / x64: in\_progress — Compile pinned PostgreSQL, vector extension and static libraries.

