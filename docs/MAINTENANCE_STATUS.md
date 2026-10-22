# Automated maintenance status

Observed: 2026-10-22T17:26:40+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.44.2](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.44.2). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 39822578673](https://github.com/Perseusxrltd/mnemion/actions/runs/39822578673) |
| ci\.yml | v4\.44\.2 | in\_progress | [Run 39815622908](https://github.com/Perseusxrltd/mnemion/actions/runs/39815622908) |
| desktop\.yml | main | in\_progress | [Run 39814732365](https://github.com/Perseusxrltd/mnemion/actions/runs/39814732365) |
| public-updates\.yml | v4\.44\.2 | success | [Run 39762122867](https://github.com/Perseusxrltd/mnemion/actions/runs/39762122867) |
| release\.yml | release/4\.44\.2 | success | [Run 39753067641](https://github.com/Perseusxrltd/mnemion/actions/runs/39753067641) |
| verify-artifacts\.yml | main | success | [Run 39761844389](https://github.com/Perseusxrltd/mnemion/actions/runs/39761844389) |
| website-release\.yml | main | success | [Run 39822578689](https://github.com/Perseusxrltd/mnemion/actions/runs/39822578689) |
| website-release\.yml | v4\.44\.2 | success | [Run 39762118327](https://github.com/Perseusxrltd/mnemion/actions/runs/39762118327) |

## Active jobs

[Run 39822578673](https://github.com/Perseusxrltd/mnemion/actions/runs/39822578673): 4/12 jobs completed; 4 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron ci && npm --prefix studio/electron test.
- supervision \(macos-15\): queued.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.

[Run 39815622908](https://github.com/Perseusxrltd/mnemion/actions/runs/39815622908): 10/12 jobs completed; 10 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.

[Run 39814732365](https://github.com/Perseusxrltd/mnemion/actions/runs/39814732365): 17/18 jobs completed; 17 succeeded.

- windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

