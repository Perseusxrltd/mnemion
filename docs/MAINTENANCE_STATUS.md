# Automated maintenance status

Observed: 2026-10-27T00:03:13+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.28](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.28). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40423189707](https://github.com/Perseusxrltd/mnemion/actions/runs/40423189707) |
| public-updates\.yml | v4\.46\.28 | success | [Run 40411258731](https://github.com/Perseusxrltd/mnemion/actions/runs/40411258731) |
| release\.yml | release/4\.46\.28 | success | [Run 40399013490](https://github.com/Perseusxrltd/mnemion/actions/runs/40399013490) |
| release\.yml | release/4\.46\.29 | success | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| release\.yml | release/4\.46\.30 | failure | [Run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100) |
| release\.yml | release/4\.46\.31 | cancelled | [Run 40417437026](https://github.com/Perseusxrltd/mnemion/actions/runs/40417437026) |
| verify-artifacts\.yml | main | success | [Run 40423232306](https://github.com/Perseusxrltd/mnemion/actions/runs/40423232306) |
| website-release\.yml | main | success | [Run 40423189752](https://github.com/Perseusxrltd/mnemion/actions/runs/40423189752) |
| website-release\.yml | v4\.46\.28 | success | [Run 40411254189](https://github.com/Perseusxrltd/mnemion/actions/runs/40411254189) |

## Active jobs

[Run 40423189707](https://github.com/Perseusxrltd/mnemion/actions/runs/40423189707): 8/12 jobs completed; 8 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.


## Unsuccessful jobs

- [Run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100): native / windows-2022 / x64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
