# Automated maintenance status

Observed: 2026-10-26T02:26:11+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.6](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.6). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40258081039](https://github.com/Perseusxrltd/mnemion/actions/runs/40258081039) |
| desktop\.yml | main | success | [Run 40251151874](https://github.com/Perseusxrltd/mnemion/actions/runs/40251151874) |
| release\.yml | release/4\.46\.10 | failure | [Run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798) |
| release\.yml | release/4\.46\.11 | failure | [Run 40254768233](https://github.com/Perseusxrltd/mnemion/actions/runs/40254768233) |
| release\.yml | release/4\.46\.12 | queued | [Run 40258369359](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359) |
| release\.yml | release/4\.46\.7 | cancelled | [Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718) |
| release\.yml | release/4\.46\.8 | cancelled | [Run 40236329055](https://github.com/Perseusxrltd/mnemion/actions/runs/40236329055) |
| release\.yml | release/4\.46\.9 | cancelled | [Run 40243385008](https://github.com/Perseusxrltd/mnemion/actions/runs/40243385008) |
| verify-artifacts\.yml | main | skipped | [Run 40258978127](https://github.com/Perseusxrltd/mnemion/actions/runs/40258978127) |
| website-release\.yml | main | success | [Run 40258080932](https://github.com/Perseusxrltd/mnemion/actions/runs/40258080932) |

## Active jobs

[Run 40258081039](https://github.com/Perseusxrltd/mnemion/actions/runs/40258081039): 8/12 jobs completed; 8 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40258369359](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359): 11/24 jobs completed; 10 succeeded.

- checks / studio: in\_progress — Verify wheel and source package include the matching web Studio.
- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- checks / legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / native\_database / Database / windows / x64: in\_progress — Set up job.
- native / native\_database / Database / linux / arm64: queued.
- native / native\_database / Database / macos / arm64: in\_progress — Set up job.
- native / native\_database / Database / macos / x64: queued.
- native / native\_database / Database / linux / x64: in\_progress.


## Unsuccessful jobs

- [Run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798): checks / service \(3\.12\) (failure). Steps: Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- [Run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798): native / windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 40254768233](https://github.com/Perseusxrltd/mnemion/actions/runs/40254768233): native / windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
