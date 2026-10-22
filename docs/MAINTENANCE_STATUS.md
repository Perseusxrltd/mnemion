# Automated maintenance status

Observed: 2026-10-22T09:16:37+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | queued | [Run 39754044036](https://github.com/Perseusxrltd/mnemion/actions/runs/39754044036) |
| public-updates\.yml | v4\.44\.1 | success | [Run 39648047355](https://github.com/Perseusxrltd/mnemion/actions/runs/39648047355) |
| release\.yml | release/4\.44\.1-r2 | success | [Run 39637945958](https://github.com/Perseusxrltd/mnemion/actions/runs/39637945958) |
| release\.yml | release/4\.44\.2 | queued | [Run 39753067641](https://github.com/Perseusxrltd/mnemion/actions/runs/39753067641) |
| verify-artifacts\.yml | main | success | [Run 39647805616](https://github.com/Perseusxrltd/mnemion/actions/runs/39647805616) |
| website-release\.yml | main | success | [Run 39754043731](https://github.com/Perseusxrltd/mnemion/actions/runs/39754043731) |
| website-release\.yml | v4\.44\.1 | success | [Run 39648042222](https://github.com/Perseusxrltd/mnemion/actions/runs/39648042222) |

## Active jobs

[Run 39754044036](https://github.com/Perseusxrltd/mnemion/actions/runs/39754044036): 4/12 jobs completed; 4 succeeded.

- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15\): queued.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- container \(ubuntu-22\.04-arm\): in\_progress — Verify the non-root image includes Studio, guides and notices offline.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39753067641](https://github.com/Perseusxrltd/mnemion/actions/runs/39753067641): 19/25 jobs completed; 18 succeeded.

- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- checks / supervision \(macos-15\): queued.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / native\_database / Database / macos / arm64: queued.

