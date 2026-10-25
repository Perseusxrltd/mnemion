# Automated maintenance status

Observed: 2026-10-25T21:35:01+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.6](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.6). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | pending | [Run 40236097267](https://github.com/Perseusxrltd/mnemion/actions/runs/40236097267) |
| database-cache\.yml | main | success | [Run 40179454634](https://github.com/Perseusxrltd/mnemion/actions/runs/40179454634) |
| release\.yml | release/4\.46\.7 | in\_progress | [Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718) |
| website-release\.yml | main | success | [Run 40236097268](https://github.com/Perseusxrltd/mnemion/actions/runs/40236097268) |

## Active jobs

[Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718): 30/32 jobs completed; 25 succeeded.

- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718): native / windows-2022 / x64 (failure). Steps: Run uv run --no-sync npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718): native / ubuntu-22\.04-arm / arm64 (failure). Steps: Run uv run --no-sync npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718): native / ubuntu-22\.04 / x64 (failure). Steps: Run uv run --no-sync npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718): native / windows-11-arm / arm64 (failure). Steps: Run uv run --no-sync npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
