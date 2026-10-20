# Automated maintenance status

Observed: 2026-10-20T14:04:23+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.40.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.40.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T13:39:27Z |
| [#46](https://github.com/Perseusxrltd/mnemion/issues/46) | Deployment access: Codex/Astra cannot see the existing office task and memory spaces | 2026-10-20T13:38:41Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39434393357](https://github.com/Perseusxrltd/mnemion/actions/runs/39434393357) |
| public-updates\.yml | v4\.40\.0 | success | [Run 39434085500](https://github.com/Perseusxrltd/mnemion/actions/runs/39434085500) |
| release\.yml | release/4\.40\.0 | success | [Run 39424241142](https://github.com/Perseusxrltd/mnemion/actions/runs/39424241142) |
| release\.yml | release/4\.41\.0 | in\_progress | [Run 39428746847](https://github.com/Perseusxrltd/mnemion/actions/runs/39428746847) |
| verify-artifacts\.yml | main | success | [Run 39433889111](https://github.com/Perseusxrltd/mnemion/actions/runs/39433889111) |
| website-release\.yml | v4\.40\.0 | success | [Run 39434081456](https://github.com/Perseusxrltd/mnemion/actions/runs/39434081456) |

## Active jobs

[Run 39434393357](https://github.com/Perseusxrltd/mnemion/actions/runs/39434393357): 9/12 jobs completed; 8 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39428746847](https://github.com/Perseusxrltd/mnemion/actions/runs/39428746847): 21/31 jobs completed; 21 succeeded.

- checks / supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / service \(3\.14\): in\_progress.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-11-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.


## Failed jobs

- [Run 39434393357](https://github.com/Perseusxrltd/mnemion/actions/runs/39434393357): supervision \(macos-15-intel\). Steps: Run python -m pip install uv==0\.12\.24.
