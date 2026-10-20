# Automated maintenance status

Observed: 2026-10-20T06:12:25+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.31.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.31.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39377250572](https://github.com/Perseusxrltd/mnemion/actions/runs/39377250572) |
| public-updates\.yml | v4\.31\.0 | success | [Run 39374937778](https://github.com/Perseusxrltd/mnemion/actions/runs/39374937778) |
| release\.yml | release/4\.31\.0-r4 | success | [Run 39371280650](https://github.com/Perseusxrltd/mnemion/actions/runs/39371280650) |
| release\.yml | release/4\.32\.0 | cancelled | [Run 39373420728](https://github.com/Perseusxrltd/mnemion/actions/runs/39373420728) |
| release\.yml | release/4\.32\.0-r2 | in\_progress | [Run 39377381706](https://github.com/Perseusxrltd/mnemion/actions/runs/39377381706) |
| verify-artifacts\.yml | main | skipped | [Run 39377325233](https://github.com/Perseusxrltd/mnemion/actions/runs/39377325233) |
| website-release\.yml | v4\.31\.0 | success | [Run 39374935509](https://github.com/Perseusxrltd/mnemion/actions/runs/39374935509) |

## Active jobs

[Run 39377381706](https://github.com/Perseusxrltd/mnemion/actions/runs/39377381706): 24/31 jobs completed; 24 succeeded.

- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Run actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / macos-15 / arm64: in\_progress — Packaged Mac update, restart guards and relaunch.

