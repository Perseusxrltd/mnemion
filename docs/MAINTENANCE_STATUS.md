# Automated maintenance status

Observed: 2026-10-20T08:39:58+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.34.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.34.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39393856803](https://github.com/Perseusxrltd/mnemion/actions/runs/39393856803) |
| public-updates\.yml | v4\.34\.0 | success | [Run 39393538181](https://github.com/Perseusxrltd/mnemion/actions/runs/39393538181) |
| release\.yml | release/4\.34\.0 | success | [Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080) |
| release\.yml | release/4\.35\.0 | in\_progress | [Run 39392435604](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604) |
| release\.yml | release/4\.36\.0 | pending | [Run 39394175777](https://github.com/Perseusxrltd/mnemion/actions/runs/39394175777) |
| verify-artifacts\.yml | main | success | [Run 39393375424](https://github.com/Perseusxrltd/mnemion/actions/runs/39393375424) |
| website-release\.yml | v4\.34\.0 | success | [Run 39393535317](https://github.com/Perseusxrltd/mnemion/actions/runs/39393535317) |

## Active jobs

[Run 39393856803](https://github.com/Perseusxrltd/mnemion/actions/runs/39393856803): 8/12 jobs completed; 8 succeeded.

- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.

[Run 39392435604](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604): 22/31 jobs completed; 22 succeeded.

- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / service \(3\.13\): in\_progress.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-11-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.

