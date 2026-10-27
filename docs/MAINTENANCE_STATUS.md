# Automated maintenance status

Observed: 2026-10-27T12:49:35+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.38](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.38). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40505069719](https://github.com/Perseusxrltd/mnemion/actions/runs/40505069719) |
| public-updates\.yml | v4\.46\.38 | success | [Run 40505169918](https://github.com/Perseusxrltd/mnemion/actions/runs/40505169918) |
| release\.yml | release/4\.46\.38 | success | [Run 40496801738](https://github.com/Perseusxrltd/mnemion/actions/runs/40496801738) |
| release\.yml | release/4\.46\.39 | in\_progress | [Run 40504681891](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891) |
| verify-artifacts\.yml | main | success | [Run 40504337244](https://github.com/Perseusxrltd/mnemion/actions/runs/40504337244) |
| website-release\.yml | main | success | [Run 40505437247](https://github.com/Perseusxrltd/mnemion/actions/runs/40505437247) |
| website-release\.yml | v4\.46\.38 | success | [Run 40505165922](https://github.com/Perseusxrltd/mnemion/actions/runs/40505165922) |

## Active jobs

[Run 40505069719](https://github.com/Perseusxrltd/mnemion/actions/runs/40505069719): 8/12 jobs completed; 8 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify both pinned local models on the actual Mac runtime.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40504681891](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891): 15/21 jobs completed; 14 succeeded.

- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

