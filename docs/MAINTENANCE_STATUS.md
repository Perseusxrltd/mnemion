# Automated maintenance status

Observed: 2026-10-28T11:09:56+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.42](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.42). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | in\_progress | [Run 40674903593](https://github.com/Perseusxrltd/mnemion/actions/runs/40674903593) |
| database-cache\.yml | main | success | [Run 40534190892](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190892) |
| public-updates\.yml | v4\.46\.42 | success | [Run 40676183666](https://github.com/Perseusxrltd/mnemion/actions/runs/40676183666) |
| release\.yml | release/4\.46\.42 | success | [Run 40540729543](https://github.com/Perseusxrltd/mnemion/actions/runs/40540729543) |
| verify-artifacts\.yml | main | failure | [Run 40550326047](https://github.com/Perseusxrltd/mnemion/actions/runs/40550326047) |
| website-release\.yml | main | success | [Run 40534190911](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190911) |
| website-release\.yml | v4\.46\.42 | success | [Run 40676191314](https://github.com/Perseusxrltd/mnemion/actions/runs/40676191314) |

## Active jobs

[Run 40674903593](https://github.com/Perseusxrltd/mnemion/actions/runs/40674903593): 11/12 jobs completed; 11 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.


## Unsuccessful jobs

- [Run 40550326047](https://github.com/Perseusxrltd/mnemion/actions/runs/40550326047): verify (failure). Steps: Scan the exact downloaded distributions before publication.
