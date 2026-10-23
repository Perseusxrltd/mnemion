# Automated maintenance status

Observed: 2026-10-23T14:50:54+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.3](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.3). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39972086704](https://github.com/Perseusxrltd/mnemion/actions/runs/39972086704) |
| public-updates\.yml | v4\.46\.3 | queued | [Run 39973022163](https://github.com/Perseusxrltd/mnemion/actions/runs/39973022163) |
| release\.yml | release/4\.46\.3 | success | [Run 39961881757](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757) |
| verify-artifacts\.yml | main | success | [Run 39972316494](https://github.com/Perseusxrltd/mnemion/actions/runs/39972316494) |
| website-release\.yml | main | success | [Run 39957182981](https://github.com/Perseusxrltd/mnemion/actions/runs/39957182981) |
| website-release\.yml | v4\.46\.3 | success | [Run 39973017198](https://github.com/Perseusxrltd/mnemion/actions/runs/39973017198) |

## Active jobs

[Run 39972086704](https://github.com/Perseusxrltd/mnemion/actions/runs/39972086704): 8/12 jobs completed; 8 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.

[Run 39973022163](https://github.com/Perseusxrltd/mnemion/actions/runs/39973022163): 1/7 jobs completed; 1 succeeded.

- windows / arm64 public upgrade: in\_progress — Run python -m pip install psutil==7\.2\.2.
- macos / arm64 public upgrade: queued.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.

