# Automated maintenance status

Observed: 2026-10-21T02:41:53+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.44.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.44.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39533277665](https://github.com/Perseusxrltd/mnemion/actions/runs/39533277665) |
| public-updates\.yml | v4\.44\.0 | in\_progress | [Run 39534394111](https://github.com/Perseusxrltd/mnemion/actions/runs/39534394111) |
| release\.yml | release/4\.44\.0 | success | [Run 39530357580](https://github.com/Perseusxrltd/mnemion/actions/runs/39530357580) |
| verify-artifacts\.yml | main | success | [Run 39534260688](https://github.com/Perseusxrltd/mnemion/actions/runs/39534260688) |
| website-release\.yml | v4\.44\.0 | success | [Run 39534391338](https://github.com/Perseusxrltd/mnemion/actions/runs/39534391338) |

## Active jobs

[Run 39533277665](https://github.com/Perseusxrltd/mnemion/actions/runs/39533277665): 8/12 jobs completed; 8 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39534394111](https://github.com/Perseusxrltd/mnemion/actions/runs/39534394111): 1/7 jobs completed; 1 succeeded.

- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Linux desktop libraries.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.

