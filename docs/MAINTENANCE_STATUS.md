# Automated maintenance status

Observed: 2026-10-26T10:35:58+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.13](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.13). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40308440212](https://github.com/Perseusxrltd/mnemion/actions/runs/40308440212) |
| database-cache\.yml | main | success | [Run 40304827056](https://github.com/Perseusxrltd/mnemion/actions/runs/40304827056) |
| public-updates\.yml | v4\.46\.13 | success | [Run 40268195296](https://github.com/Perseusxrltd/mnemion/actions/runs/40268195296) |
| release\.yml | release/4\.46\.13 | success | [Run 40262676121](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121) |
| release\.yml | release/4\.46\.14 | failure | [Run 40286600426](https://github.com/Perseusxrltd/mnemion/actions/runs/40286600426) |
| release\.yml | release/4\.46\.15 | failure | [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655) |
| release\.yml | release/4\.46\.17 | in\_progress | [Run 40303268742](https://github.com/Perseusxrltd/mnemion/actions/runs/40303268742) |
| verify-artifacts\.yml | main | skipped | [Run 40296033009](https://github.com/Perseusxrltd/mnemion/actions/runs/40296033009) |
| website-release\.yml | main | success | [Run 40308440222](https://github.com/Perseusxrltd/mnemion/actions/runs/40308440222) |
| website-release\.yml | v4\.46\.13 | success | [Run 40268192045](https://github.com/Perseusxrltd/mnemion/actions/runs/40268192045) |

## Active jobs

[Run 40308440212](https://github.com/Perseusxrltd/mnemion/actions/runs/40308440212): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.14\): in\_progress — Initialize containers.
- service \(3\.12\): in\_progress — Initialize containers.
- service \(3\.13\): in\_progress — Initialize containers.
- supervision \(macos-15-intel\): in\_progress — Compile and exercise the native network admission probe in Python and Node.

[Run 40303268742](https://github.com/Perseusxrltd/mnemion/actions/runs/40303268742): 20/21 jobs completed; 18 succeeded.

- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 40286600426](https://github.com/Perseusxrltd/mnemion/actions/runs/40286600426): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / ubuntu-22\.04 / x64 (failure). Steps: Package the native desktop with one bounded upstream-download retry, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / windows-2022 / x64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / macos-15 / arm64 (failure). Steps: Package the native desktop with one bounded upstream-download retry, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / ubuntu-22\.04-arm / arm64 (failure). Steps: Package the native desktop with one bounded upstream-download retry, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / macos-15-intel / x64 (failure). Steps: Package the native desktop with one bounded upstream-download retry, Retain generated desktop-content secret scan receipt.
- [Run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40303268742](https://github.com/Perseusxrltd/mnemion/actions/runs/40303268742): native / macos-15 / arm64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
