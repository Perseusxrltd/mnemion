# Automated maintenance status

Observed: 2026-10-21T17:30:57+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | queued | [Run 39644195180](https://github.com/Perseusxrltd/mnemion/actions/runs/39644195180) |
| database-cache\.yml | main | success | [Run 39576347122](https://github.com/Perseusxrltd/mnemion/actions/runs/39576347122) |
| desktop\.yml | main | success | [Run 39628117517](https://github.com/Perseusxrltd/mnemion/actions/runs/39628117517) |
| release\.yml | release/4\.44\.1 | failure | [Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686) |
| release\.yml | release/4\.44\.1-r2 | in\_progress | [Run 39637945958](https://github.com/Perseusxrltd/mnemion/actions/runs/39637945958) |
| verify-artifacts\.yml | main | skipped | [Run 39639569502](https://github.com/Perseusxrltd/mnemion/actions/runs/39639569502) |
| website-release\.yml | main | success | [Run 39644195219](https://github.com/Perseusxrltd/mnemion/actions/runs/39644195219) |

## Active jobs

[Run 39644195180](https://github.com/Perseusxrltd/mnemion/actions/runs/39644195180): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix packages/client test.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15\): queued.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.12\): in\_progress — Run uv sync --locked --python 3\.12 --group dev.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.

[Run 39637945958](https://github.com/Perseusxrltd/mnemion/actions/runs/39637945958): 29/32 jobs completed; 28 succeeded.

- native / windows-2022 / x64: in\_progress — Native Windows installation, authenticated upgrade and relaunch.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686): checks / supervision \(macos-15\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686): native / windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686): native / ubuntu-22\.04 / x64 (failure). No unsuccessful step was reported.
