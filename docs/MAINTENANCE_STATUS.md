# Automated maintenance status

Observed: 2026-10-21T11:31:42+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | in\_progress | [Run 39592497905](https://github.com/Perseusxrltd/mnemion/actions/runs/39592497905) |
| database-cache\.yml | main | success | [Run 39576347122](https://github.com/Perseusxrltd/mnemion/actions/runs/39576347122) |
| desktop\.yml | main | failure | [Run 39588502974](https://github.com/Perseusxrltd/mnemion/actions/runs/39588502974) |
| public-updates\.yml | v4\.44\.0 | success | [Run 39534394111](https://github.com/Perseusxrltd/mnemion/actions/runs/39534394111) |
| release\.yml | release/4\.44\.0 | success | [Run 39530357580](https://github.com/Perseusxrltd/mnemion/actions/runs/39530357580) |
| verify-artifacts\.yml | main | success | [Run 39534260688](https://github.com/Perseusxrltd/mnemion/actions/runs/39534260688) |
| website-release\.yml | main | success | [Run 39592497883](https://github.com/Perseusxrltd/mnemion/actions/runs/39592497883) |
| website-release\.yml | v4\.44\.0 | success | [Run 39534391338](https://github.com/Perseusxrltd/mnemion/actions/runs/39534391338) |

## Active jobs

[Run 39592497905](https://github.com/Perseusxrltd/mnemion/actions/runs/39592497905): 4/12 jobs completed; 4 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron ci && npm --prefix studio/electron test.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.


## Unsuccessful jobs

- [Run 39588502974](https://github.com/Perseusxrltd/mnemion/actions/runs/39588502974): windows-2022 / x64 (failure). Steps: Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
- [Run 39588502974](https://github.com/Perseusxrltd/mnemion/actions/runs/39588502974): windows-11-arm / arm64 (failure). Steps: Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
- [Run 39588502974](https://github.com/Perseusxrltd/mnemion/actions/runs/39588502974): macos-15 / arm64 (failure). Steps: Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
- [Run 39588502974](https://github.com/Perseusxrltd/mnemion/actions/runs/39588502974): ubuntu-22\.04-arm / arm64 (failure). Steps: Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
- [Run 39588502974](https://github.com/Perseusxrltd/mnemion/actions/runs/39588502974): macos-15-intel / x64 (failure). Steps: Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
- [Run 39588502974](https://github.com/Perseusxrltd/mnemion/actions/runs/39588502974): ubuntu-22\.04 / x64 (failure). Steps: Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
