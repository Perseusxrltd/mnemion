# Automated maintenance status

Observed: 2026-10-21T14:52:22+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | queued | [Run 39620599958](https://github.com/Perseusxrltd/mnemion/actions/runs/39620599958) |
| database-cache\.yml | main | success | [Run 39576347122](https://github.com/Perseusxrltd/mnemion/actions/runs/39576347122) |
| desktop\.yml | main | in\_progress | [Run 39613577682](https://github.com/Perseusxrltd/mnemion/actions/runs/39613577682) |
| public-updates\.yml | v4\.44\.0 | success | [Run 39534394111](https://github.com/Perseusxrltd/mnemion/actions/runs/39534394111) |
| release\.yml | release/4\.44\.0 | success | [Run 39530357580](https://github.com/Perseusxrltd/mnemion/actions/runs/39530357580) |
| verify-artifacts\.yml | main | success | [Run 39534260688](https://github.com/Perseusxrltd/mnemion/actions/runs/39534260688) |
| website-release\.yml | main | queued | [Run 39620599994](https://github.com/Perseusxrltd/mnemion/actions/runs/39620599994) |
| website-release\.yml | v4\.44\.0 | success | [Run 39534391338](https://github.com/Perseusxrltd/mnemion/actions/runs/39534391338) |

## Active jobs

[Run 39620599958](https://github.com/Perseusxrltd/mnemion/actions/runs/39620599958): 1/12 jobs completed; 1 succeeded.

- Select checks: queued.
- studio: queued.
- dependency-audit: queued.
- service \(3\.13\): queued.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15\): queued.
- supervision \(macos-15-intel\): queued.
- service \(3\.12\): in\_progress — Initialize containers.
- service \(3\.14\): in\_progress — Initialize containers.
- container \(ubuntu-22\.04-arm\): queued.
- container \(ubuntu-22\.04\): queued.

[Run 39613577682](https://github.com/Perseusxrltd/mnemion/actions/runs/39613577682): 17/18 jobs completed; 15 succeeded.

- windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

[Run 39620599994](https://github.com/Perseusxrltd/mnemion/actions/runs/39620599994): 0/1 jobs completed; 0 succeeded.

- synchronize: in\_progress.


## Unsuccessful jobs

- [Run 39613577682](https://github.com/Perseusxrltd/mnemion/actions/runs/39613577682): macos-15-intel / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39613577682](https://github.com/Perseusxrltd/mnemion/actions/runs/39613577682): macos-15 / arm64 (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
