# Automated maintenance status

Observed: 2026-10-23T19:11:44+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.4](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.4). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40009317328](https://github.com/Perseusxrltd/mnemion/actions/runs/40009317328) |
| public-updates\.yml | v4\.46\.4 | success | [Run 40005404536](https://github.com/Perseusxrltd/mnemion/actions/runs/40005404536) |
| release\.yml | release/4\.46\.4 | success | [Run 39997298864](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864) |
| release\.yml | release/4\.46\.5 | in\_progress | [Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734) |
| verify-artifacts\.yml | main | success | [Run 40004648689](https://github.com/Perseusxrltd/mnemion/actions/runs/40004648689) |
| website-release\.yml | main | success | [Run 40009317318](https://github.com/Perseusxrltd/mnemion/actions/runs/40009317318) |
| website-release\.yml | v4\.46\.4 | success | [Run 40005399880](https://github.com/Perseusxrltd/mnemion/actions/runs/40005399880) |

## Active jobs

[Run 40009317328](https://github.com/Perseusxrltd/mnemion/actions/runs/40009317328): 4/12 jobs completed; 4 succeeded.

- studio: in\_progress — Independent host control through the real desktop profile and native engine.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04-arm\): in\_progress — Verify the non-root image includes Studio, guides and notices offline.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734): 31/32 jobs completed; 29 succeeded.

- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734): native / windows-11-arm / arm64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
