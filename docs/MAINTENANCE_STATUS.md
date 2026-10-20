# Automated maintenance status

Observed: 2026-10-20T05:35:49+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.31.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.31.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39375543254](https://github.com/Perseusxrltd/mnemion/actions/runs/39375543254) |
| public-updates\.yml | v4\.31\.0 | in\_progress | [Run 39374937778](https://github.com/Perseusxrltd/mnemion/actions/runs/39374937778) |
| release\.yml | release/4\.31\.0-r4 | success | [Run 39371280650](https://github.com/Perseusxrltd/mnemion/actions/runs/39371280650) |
| release\.yml | release/4\.32\.0 | in\_progress | [Run 39373420728](https://github.com/Perseusxrltd/mnemion/actions/runs/39373420728) |
| verify-artifacts\.yml | main | success | [Run 39374776534](https://github.com/Perseusxrltd/mnemion/actions/runs/39374776534) |
| website-release\.yml | v4\.31\.0 | success | [Run 39374935509](https://github.com/Perseusxrltd/mnemion/actions/runs/39374935509) |

## Active jobs

[Run 39375543254](https://github.com/Perseusxrltd/mnemion/actions/runs/39375543254): 7/8 jobs completed; 2 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron audit --audit-level=high.

[Run 39374937778](https://github.com/Perseusxrltd/mnemion/actions/runs/39374937778): 5/7 jobs completed; 5 succeeded.

- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 39373420728](https://github.com/Perseusxrltd/mnemion/actions/runs/39373420728): 22/31 jobs completed; 22 succeeded.

- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / ubuntu-22\.04 / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / macos-15-intel / x64: in\_progress — Locked native service build dependencies.
- native / macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

