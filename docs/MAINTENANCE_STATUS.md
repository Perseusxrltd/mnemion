# Automated maintenance status

Observed: 2026-10-23T07:17:26+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39916297399](https://github.com/Perseusxrltd/mnemion/actions/runs/39916297399) |
| public-updates\.yml | v4\.46\.0 | success | [Run 39907316827](https://github.com/Perseusxrltd/mnemion/actions/runs/39907316827) |
| release\.yml | release/4\.46\.0-r2 | success | [Run 39895069093](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093) |
| release\.yml | release/4\.46\.1 | in\_progress | [Run 39913638457](https://github.com/Perseusxrltd/mnemion/actions/runs/39913638457) |
| release\.yml | release/4\.46\.1-r2 | pending | [Run 39916372505](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505) |
| verify-artifacts\.yml | main | failure | [Run 39901894314](https://github.com/Perseusxrltd/mnemion/actions/runs/39901894314) |
| website-release\.yml | main | success | [Run 39916297432](https://github.com/Perseusxrltd/mnemion/actions/runs/39916297432) |
| website-release\.yml | v4\.46\.0 | success | [Run 39907323013](https://github.com/Perseusxrltd/mnemion/actions/runs/39907323013) |

## Active jobs

[Run 39916297399](https://github.com/Perseusxrltd/mnemion/actions/runs/39916297399): 5/12 jobs completed; 5 succeeded.

- studio: in\_progress.
- legacy: in\_progress.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): in\_progress — Verify both pinned local models on the actual Mac runtime.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39913638457](https://github.com/Perseusxrltd/mnemion/actions/runs/39913638457): 29/32 jobs completed; 27 succeeded.

- checks / service \(3\.12\): in\_progress.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 39913638457](https://github.com/Perseusxrltd/mnemion/actions/runs/39913638457): native / windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39901894314](https://github.com/Perseusxrltd/mnemion/actions/runs/39901894314): verify (failure). Steps: Scan the exact downloaded distributions before publication.
