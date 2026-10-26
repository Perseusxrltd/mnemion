# Automated maintenance status

Observed: 2026-10-26T22:52:57+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.28](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.28). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40413510185](https://github.com/Perseusxrltd/mnemion/actions/runs/40413510185) |
| public-updates\.yml | v4\.46\.28 | success | [Run 40411258731](https://github.com/Perseusxrltd/mnemion/actions/runs/40411258731) |
| release\.yml | release/4\.46\.28 | success | [Run 40399013490](https://github.com/Perseusxrltd/mnemion/actions/runs/40399013490) |
| release\.yml | release/4\.46\.29 | in\_progress | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| release\.yml | release/4\.46\.30 | pending | [Run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100) |
| verify-artifacts\.yml | main | success | [Run 40410428285](https://github.com/Perseusxrltd/mnemion/actions/runs/40410428285) |
| website-release\.yml | main | success | [Run 40415692444](https://github.com/Perseusxrltd/mnemion/actions/runs/40415692444) |
| website-release\.yml | v4\.46\.28 | success | [Run 40411254189](https://github.com/Perseusxrltd/mnemion/actions/runs/40411254189) |

## Active jobs

[Run 40413510185](https://github.com/Perseusxrltd/mnemion/actions/runs/40413510185): 9/12 jobs completed; 9 succeeded.

- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477): 20/21 jobs completed; 19 succeeded.

- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

