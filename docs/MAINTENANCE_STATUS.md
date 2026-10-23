# Automated maintenance status

Observed: 2026-10-23T12:25:41+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.2](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.2). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39953101845](https://github.com/Perseusxrltd/mnemion/actions/runs/39953101845) |
| public-updates\.yml | v4\.46\.2 | in\_progress | [Run 39952552845](https://github.com/Perseusxrltd/mnemion/actions/runs/39952552845) |
| release\.yml | release/4\.46\.2 | success | [Run 39945380878](https://github.com/Perseusxrltd/mnemion/actions/runs/39945380878) |
| verify-artifacts\.yml | main | success | [Run 39951889805](https://github.com/Perseusxrltd/mnemion/actions/runs/39951889805) |
| website-release\.yml | main | success | [Run 39953101926](https://github.com/Perseusxrltd/mnemion/actions/runs/39953101926) |
| website-release\.yml | v4\.46\.2 | success | [Run 39952548379](https://github.com/Perseusxrltd/mnemion/actions/runs/39952548379) |

## Active jobs

[Run 39953101845](https://github.com/Perseusxrltd/mnemion/actions/runs/39953101845): 5/12 jobs completed; 5 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron ci && npm --prefix studio/electron test.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.13\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.

[Run 39952552845](https://github.com/Perseusxrltd/mnemion/actions/runs/39952552845): 4/7 jobs completed; 4 succeeded.

- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.

