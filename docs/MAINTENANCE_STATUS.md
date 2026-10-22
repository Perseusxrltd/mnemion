# Automated maintenance status

Observed: 2026-10-22T09:27:41+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.44.1](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.44.1). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39754044036](https://github.com/Perseusxrltd/mnemion/actions/runs/39754044036) |
| database-cache\.yml | main | success | [Run 39755197344](https://github.com/Perseusxrltd/mnemion/actions/runs/39755197344) |
| public-updates\.yml | v4\.44\.1 | success | [Run 39648047355](https://github.com/Perseusxrltd/mnemion/actions/runs/39648047355) |
| release\.yml | release/4\.44\.1-r2 | success | [Run 39637945958](https://github.com/Perseusxrltd/mnemion/actions/runs/39637945958) |
| release\.yml | release/4\.44\.2 | in\_progress | [Run 39753067641](https://github.com/Perseusxrltd/mnemion/actions/runs/39753067641) |
| verify-artifacts\.yml | main | success | [Run 39647805616](https://github.com/Perseusxrltd/mnemion/actions/runs/39647805616) |
| website-release\.yml | main | success | [Run 39754043731](https://github.com/Perseusxrltd/mnemion/actions/runs/39754043731) |
| website-release\.yml | v4\.44\.1 | success | [Run 39648042222](https://github.com/Perseusxrltd/mnemion/actions/runs/39648042222) |

## Active jobs

[Run 39754044036](https://github.com/Perseusxrltd/mnemion/actions/runs/39754044036): 8/12 jobs completed; 8 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39753067641](https://github.com/Perseusxrltd/mnemion/actions/runs/39753067641): 25/27 jobs completed; 21 succeeded.

- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.


## Unsuccessful jobs

- [Run 39753067641](https://github.com/Perseusxrltd/mnemion/actions/runs/39753067641): native / native\_database / Database / macos / arm64 (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
