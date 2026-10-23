# Automated maintenance status

Observed: 2026-10-23T18:42:25+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.4](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.4). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40001971973](https://github.com/Perseusxrltd/mnemion/actions/runs/40001971973) |
| public-updates\.yml | v4\.46\.4 | in\_progress | [Run 40005404536](https://github.com/Perseusxrltd/mnemion/actions/runs/40005404536) |
| release\.yml | release/4\.46\.4 | success | [Run 39997298864](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864) |
| release\.yml | release/4\.46\.5 | queued | [Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734) |
| verify-artifacts\.yml | main | success | [Run 40004648689](https://github.com/Perseusxrltd/mnemion/actions/runs/40004648689) |
| website-release\.yml | main | success | [Run 39989203575](https://github.com/Perseusxrltd/mnemion/actions/runs/39989203575) |
| website-release\.yml | v4\.46\.4 | success | [Run 40005399880](https://github.com/Perseusxrltd/mnemion/actions/runs/40005399880) |

## Active jobs

[Run 40005404536](https://github.com/Perseusxrltd/mnemion/actions/runs/40005404536): 1/7 jobs completed; 1 succeeded.

- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Linux desktop libraries.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734): 20/25 jobs completed; 19 succeeded.

- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / native\_database / Database / macos / arm64: queued.

