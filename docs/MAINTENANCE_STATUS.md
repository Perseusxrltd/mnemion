# Automated maintenance status

Observed: 2026-10-21T17:54:08+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | in\_progress | [Run 39644195180](https://github.com/Perseusxrltd/mnemion/actions/runs/39644195180) |
| database-cache\.yml | main | success | [Run 39576347122](https://github.com/Perseusxrltd/mnemion/actions/runs/39576347122) |
| desktop\.yml | main | success | [Run 39628117517](https://github.com/Perseusxrltd/mnemion/actions/runs/39628117517) |
| release\.yml | release/4\.44\.1 | failure | [Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686) |
| release\.yml | release/4\.44\.1-r2 | success | [Run 39637945958](https://github.com/Perseusxrltd/mnemion/actions/runs/39637945958) |
| verify-artifacts\.yml | main | in\_progress | [Run 39647805616](https://github.com/Perseusxrltd/mnemion/actions/runs/39647805616) |
| website-release\.yml | main | success | [Run 39645475009](https://github.com/Perseusxrltd/mnemion/actions/runs/39645475009) |

## Active jobs

[Run 39644195180](https://github.com/Perseusxrltd/mnemion/actions/runs/39644195180): 11/12 jobs completed; 10 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39647805616](https://github.com/Perseusxrltd/mnemion/actions/runs/39647805616): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.


## Unsuccessful jobs

- [Run 39644195180](https://github.com/Perseusxrltd/mnemion/actions/runs/39644195180): supervision \(macos-15\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686): checks / supervision \(macos-15\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686): native / windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686): native / ubuntu-22\.04 / x64 (failure). No unsuccessful step was reported.
