# Automated maintenance status

Observed: 2026-10-26T13:32:07+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.13](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.13). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40328700855](https://github.com/Perseusxrltd/mnemion/actions/runs/40328700855) |
| database-cache\.yml | main | success | [Run 40304827056](https://github.com/Perseusxrltd/mnemion/actions/runs/40304827056) |
| desktop\.yml | main | success | [Run 40324338816](https://github.com/Perseusxrltd/mnemion/actions/runs/40324338816) |
| public-updates\.yml | v4\.46\.13 | success | [Run 40268195296](https://github.com/Perseusxrltd/mnemion/actions/runs/40268195296) |
| release\.yml | release/4\.46\.13 | success | [Run 40262676121](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121) |
| release\.yml | release/4\.46\.14 | failure | [Run 40286600426](https://github.com/Perseusxrltd/mnemion/actions/runs/40286600426) |
| release\.yml | release/4\.46\.15 | failure | [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655) |
| release\.yml | release/4\.46\.17 | failure | [Run 40303268742](https://github.com/Perseusxrltd/mnemion/actions/runs/40303268742) |
| verify-artifacts\.yml | main | skipped | [Run 40310282067](https://github.com/Perseusxrltd/mnemion/actions/runs/40310282067) |
| website-release\.yml | main | success | [Run 40331282606](https://github.com/Perseusxrltd/mnemion/actions/runs/40331282606) |
| website-release\.yml | v4\.46\.13 | success | [Run 40268192045](https://github.com/Perseusxrltd/mnemion/actions/runs/40268192045) |

## Active jobs

[Run 40328700855](https://github.com/Perseusxrltd/mnemion/actions/runs/40328700855): 9/12 jobs completed; 9 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.


## Unsuccessful jobs

- [Run 40286600426](https://github.com/Perseusxrltd/mnemion/actions/runs/40286600426): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / ubuntu-22\.04 / x64 (failure). Steps: Package the native desktop with one bounded upstream-download retry, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / windows-2022 / x64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / macos-15 / arm64 (failure). Steps: Package the native desktop with one bounded upstream-download retry, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / ubuntu-22\.04-arm / arm64 (failure). Steps: Package the native desktop with one bounded upstream-download retry, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / macos-15-intel / x64 (failure). Steps: Package the native desktop with one bounded upstream-download retry, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40303268742](https://github.com/Perseusxrltd/mnemion/actions/runs/40303268742): native / macos-15 / arm64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
