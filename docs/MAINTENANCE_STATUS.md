# Automated maintenance status

Observed: 2026-10-26T02:37:42+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.6](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.6). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40259911807](https://github.com/Perseusxrltd/mnemion/actions/runs/40259911807) |
| desktop\.yml | main | success | [Run 40251151874](https://github.com/Perseusxrltd/mnemion/actions/runs/40251151874) |
| release\.yml | release/4\.46\.10 | failure | [Run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798) |
| release\.yml | release/4\.46\.11 | failure | [Run 40254768233](https://github.com/Perseusxrltd/mnemion/actions/runs/40254768233) |
| release\.yml | release/4\.46\.12 | in\_progress | [Run 40258369359](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359) |
| release\.yml | release/4\.46\.7 | cancelled | [Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718) |
| release\.yml | release/4\.46\.8 | cancelled | [Run 40236329055](https://github.com/Perseusxrltd/mnemion/actions/runs/40236329055) |
| release\.yml | release/4\.46\.9 | cancelled | [Run 40243385008](https://github.com/Perseusxrltd/mnemion/actions/runs/40243385008) |
| verify-artifacts\.yml | main | skipped | [Run 40258978127](https://github.com/Perseusxrltd/mnemion/actions/runs/40258978127) |
| website-release\.yml | main | success | [Run 40259911830](https://github.com/Perseusxrltd/mnemion/actions/runs/40259911830) |

## Active jobs

[Run 40259911807](https://github.com/Perseusxrltd/mnemion/actions/runs/40259911807): 4/12 jobs completed; 4 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron test.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.

[Run 40258369359](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359): 22/32 jobs completed; 21 succeeded.

- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798): checks / service \(3\.12\) (failure). Steps: Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- [Run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798): native / windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 40254768233](https://github.com/Perseusxrltd/mnemion/actions/runs/40254768233): native / windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
