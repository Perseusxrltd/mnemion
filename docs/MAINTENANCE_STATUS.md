# Automated maintenance status

Observed: 2026-10-22T10:29:48+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | in\_progress | [Run 39763423936](https://github.com/Perseusxrltd/mnemion/actions/runs/39763423936) |
| public-updates\.yml | v4\.44\.2 | in\_progress | [Run 39762122867](https://github.com/Perseusxrltd/mnemion/actions/runs/39762122867) |
| release\.yml | release/4\.44\.2 | success | [Run 39753067641](https://github.com/Perseusxrltd/mnemion/actions/runs/39753067641) |
| verify-artifacts\.yml | main | success | [Run 39761844389](https://github.com/Perseusxrltd/mnemion/actions/runs/39761844389) |
| website-release\.yml | main | success | [Run 39763423746](https://github.com/Perseusxrltd/mnemion/actions/runs/39763423746) |
| website-release\.yml | v4\.44\.2 | success | [Run 39762118327](https://github.com/Perseusxrltd/mnemion/actions/runs/39762118327) |

## Active jobs

[Run 39763423936](https://github.com/Perseusxrltd/mnemion/actions/runs/39763423936): 5/12 jobs completed; 5 succeeded.

- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.14\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.13\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39762122867](https://github.com/Perseusxrltd/mnemion/actions/runs/39762122867): 5/7 jobs completed; 5 succeeded.

- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.

