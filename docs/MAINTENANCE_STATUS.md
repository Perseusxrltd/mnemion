# Automated maintenance status

Observed: 2026-10-28T12:20:40+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | in\_progress | [Run 40684523128](https://github.com/Perseusxrltd/mnemion/actions/runs/40684523128) |
| database-cache\.yml | main | success | [Run 40534190892](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190892) |
| public-updates\.yml | v4\.46\.42 | success | [Run 40676183666](https://github.com/Perseusxrltd/mnemion/actions/runs/40676183666) |
| release\.yml | release/4\.46\.42 | success | [Run 40540729543](https://github.com/Perseusxrltd/mnemion/actions/runs/40540729543) |
| release\.yml | release/4\.46\.43 | queued | [Run 40684769321](https://github.com/Perseusxrltd/mnemion/actions/runs/40684769321) |
| verify-artifacts\.yml | main | skipped | [Run 40686932960](https://github.com/Perseusxrltd/mnemion/actions/runs/40686932960) |
| website-release\.yml | main | success | [Run 40684523123](https://github.com/Perseusxrltd/mnemion/actions/runs/40684523123) |
| website-release\.yml | v4\.46\.42 | success | [Run 40676191314](https://github.com/Perseusxrltd/mnemion/actions/runs/40676191314) |

## Active jobs

[Run 40684523128](https://github.com/Perseusxrltd/mnemion/actions/runs/40684523128): 9/12 jobs completed; 8 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40684769321](https://github.com/Perseusxrltd/mnemion/actions/runs/40684769321): 13/14 jobs completed; 12 succeeded.

- native / native\_database / Database / macos / arm64: queued.


## Unsuccessful jobs

- [Run 40684523128](https://github.com/Perseusxrltd/mnemion/actions/runs/40684523128): supervision \(macos-26\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
