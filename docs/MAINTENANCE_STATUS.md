# Automated maintenance status

Observed: 2026-10-25T22:06:03+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.6](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.6). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40238507907](https://github.com/Perseusxrltd/mnemion/actions/runs/40238507907) |
| database-cache\.yml | main | success | [Run 40179454634](https://github.com/Perseusxrltd/mnemion/actions/runs/40179454634) |
| release\.yml | release/4\.46\.7 | cancelled | [Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718) |
| release\.yml | release/4\.46\.8 | in\_progress | [Run 40236329055](https://github.com/Perseusxrltd/mnemion/actions/runs/40236329055) |
| verify-artifacts\.yml | main | skipped | [Run 40236493226](https://github.com/Perseusxrltd/mnemion/actions/runs/40236493226) |
| website-release\.yml | main | success | [Run 40238507937](https://github.com/Perseusxrltd/mnemion/actions/runs/40238507937) |

## Active jobs

[Run 40238507907](https://github.com/Perseusxrltd/mnemion/actions/runs/40238507907): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/frontend run test:telemetry.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15-intel\): in\_progress — Run python -m pip install uv==0\.12\.24.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.

[Run 40236329055](https://github.com/Perseusxrltd/mnemion/actions/runs/40236329055): 28/32 jobs completed; 27 succeeded.

- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Run npm --prefix studio/electron test.
- native / windows-2022 / x64: in\_progress — Run npm --prefix studio/electron test.

