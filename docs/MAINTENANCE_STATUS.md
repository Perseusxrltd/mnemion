# Automated maintenance status

Observed: 2026-10-28T10:15:00+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.40](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.40). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#47](https://github.com/Perseusxrltd/mnemion/issues/47) | Field report \(4\.46\.40\): multi-agent usage audit — slow/hanging search, suspended connector scope, noisy activity log, unusable vault over MCP, and features left unused | 2026-10-28T08:51:41Z |
| [#48](https://github.com/Perseusxrltd/mnemion/issues/48) | Mnemion as the single system: full replacement of LEDGER/DISPATCH/files, plus vault compatibility | 2026-10-28T09:04:09Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | codex/telemetry-sql-reads-20261027 | failure | [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882) |
| ci\.yml | main | in\_progress | [Run 40670480646](https://github.com/Perseusxrltd/mnemion/actions/runs/40670480646) |
| database-cache\.yml | main | success | [Run 40534190892](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190892) |
| public-updates\.yml | v4\.46\.40 | failure | [Run 40528686080](https://github.com/Perseusxrltd/mnemion/actions/runs/40528686080) |
| release\.yml | release/4\.46\.40 | success | [Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119) |
| release\.yml | release/4\.46\.41 | failure | [Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699) |
| release\.yml | release/4\.46\.42 | success | [Run 40540729543](https://github.com/Perseusxrltd/mnemion/actions/runs/40540729543) |
| verify-artifacts\.yml | main | failure | [Run 40550326047](https://github.com/Perseusxrltd/mnemion/actions/runs/40550326047) |
| website-release\.yml | main | success | [Run 40670480597](https://github.com/Perseusxrltd/mnemion/actions/runs/40670480597) |
| website-release\.yml | v4\.46\.40 | success | [Run 40528680423](https://github.com/Perseusxrltd/mnemion/actions/runs/40528680423) |

## Active jobs

[Run 40670480646](https://github.com/Perseusxrltd/mnemion/actions/runs/40670480646): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Verify wheel and source package include the matching web Studio.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-26\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.13\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.


## Unsuccessful jobs

- [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882): supervision \(macos-15\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40528686080](https://github.com/Perseusxrltd/mnemion/actions/runs/40528686080): macos / arm64 public upgrade (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699): native / native\_database / Database / macos / arm64 (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40550326047](https://github.com/Perseusxrltd/mnemion/actions/runs/40550326047): verify (failure). Steps: Scan the exact downloaded distributions before publication.
