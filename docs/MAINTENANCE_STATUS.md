# Automated maintenance status

Observed: 2026-10-26T00:47:48+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | in\_progress | [Run 40250939420](https://github.com/Perseusxrltd/mnemion/actions/runs/40250939420) |
| database-cache\.yml | main | success | [Run 40179454634](https://github.com/Perseusxrltd/mnemion/actions/runs/40179454634) |
| release\.yml | release/4\.46\.10 | failure | [Run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798) |
| release\.yml | release/4\.46\.7 | cancelled | [Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718) |
| release\.yml | release/4\.46\.8 | cancelled | [Run 40236329055](https://github.com/Perseusxrltd/mnemion/actions/runs/40236329055) |
| release\.yml | release/4\.46\.9 | cancelled | [Run 40243385008](https://github.com/Perseusxrltd/mnemion/actions/runs/40243385008) |
| verify-artifacts\.yml | main | skipped | [Run 40249478892](https://github.com/Perseusxrltd/mnemion/actions/runs/40249478892) |
| website-release\.yml | main | success | [Run 40250939496](https://github.com/Perseusxrltd/mnemion/actions/runs/40250939496) |

## Active jobs

[Run 40250939420](https://github.com/Perseusxrltd/mnemion/actions/runs/40250939420): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Initialize containers.
- service \(3\.13\): in\_progress — Run actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Run actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38.
- service \(3\.14\): in\_progress — Run actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.


## Unsuccessful jobs

- [Run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798): checks / service \(3\.12\) (failure). Steps: Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- [Run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798): native / windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
