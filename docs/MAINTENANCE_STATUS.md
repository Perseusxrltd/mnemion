# Automated maintenance status

Observed: 2026-10-27T00:04:45+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.29](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.29). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40423189707](https://github.com/Perseusxrltd/mnemion/actions/runs/40423189707) |
| public-updates\.yml | v4\.46\.29 | in\_progress | [Run 40423899386](https://github.com/Perseusxrltd/mnemion/actions/runs/40423899386) |
| release\.yml | release/4\.46\.29 | success | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| verify-artifacts\.yml | main | failure | [Run 40417189624](https://github.com/Perseusxrltd/mnemion/actions/runs/40417189624) |
| website-release\.yml | main | success | [Run 40398877004](https://github.com/Perseusxrltd/mnemion/actions/runs/40398877004) |
| website-release\.yml | v4\.46\.29 | success | [Run 40423894613](https://github.com/Perseusxrltd/mnemion/actions/runs/40423894613) |

## Active jobs

[Run 40423189707](https://github.com/Perseusxrltd/mnemion/actions/runs/40423189707): 8/12 jobs completed; 8 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40423899386](https://github.com/Perseusxrltd/mnemion/actions/runs/40423899386): 1/7 jobs completed; 1 succeeded.

- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.


## Unsuccessful jobs

- [Run 40417189624](https://github.com/Perseusxrltd/mnemion/actions/runs/40417189624): verify (failure). Steps: Scan the exact downloaded distributions before publication.
