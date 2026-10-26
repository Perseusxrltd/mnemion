# Automated maintenance status

Observed: 2026-10-26T15:15:12+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.19](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.19). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40345454839](https://github.com/Perseusxrltd/mnemion/actions/runs/40345454839) |
| public-updates\.yml | v4\.46\.19 | success | [Run 40344852373](https://github.com/Perseusxrltd/mnemion/actions/runs/40344852373) |
| release\.yml | release/4\.46\.19 | success | [Run 40333990605](https://github.com/Perseusxrltd/mnemion/actions/runs/40333990605) |
| verify-artifacts\.yml | main | success | [Run 40343874190](https://github.com/Perseusxrltd/mnemion/actions/runs/40343874190) |
| website-release\.yml | main | success | [Run 40345454886](https://github.com/Perseusxrltd/mnemion/actions/runs/40345454886) |
| website-release\.yml | v4\.46\.19 | success | [Run 40344847819](https://github.com/Perseusxrltd/mnemion/actions/runs/40344847819) |

## Active jobs

[Run 40345454839](https://github.com/Perseusxrltd/mnemion/actions/runs/40345454839): 8/12 jobs completed; 8 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

