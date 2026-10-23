# Automated maintenance status

Observed: 2026-10-23T05:25:15+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.45.1](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.45.1). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39905068103](https://github.com/Perseusxrltd/mnemion/actions/runs/39905068103) |
| public-updates\.yml | v4\.45\.1 | success | [Run 39876903393](https://github.com/Perseusxrltd/mnemion/actions/runs/39876903393) |
| release\.yml | release/4\.45\.1-r2 | success | [Run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559) |
| release\.yml | release/4\.46\.0 | failure | [Run 39884444351](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351) |
| release\.yml | release/4\.46\.0-r2 | success | [Run 39895069093](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093) |
| verify-artifacts\.yml | main | failure | [Run 39905111700](https://github.com/Perseusxrltd/mnemion/actions/runs/39905111700) |
| website-release\.yml | main | success | [Run 39905082711](https://github.com/Perseusxrltd/mnemion/actions/runs/39905082711) |
| website-release\.yml | v4\.45\.1 | success | [Run 39876908629](https://github.com/Perseusxrltd/mnemion/actions/runs/39876908629) |

## Active jobs

[Run 39905068103](https://github.com/Perseusxrltd/mnemion/actions/runs/39905068103): 8/12 jobs completed; 8 succeeded.

- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.


## Unsuccessful jobs

- [Run 39884444351](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351): native / windows-2022 / x64 (failure). Steps: Packaged window, sandboxed bridge, and local client.
- [Run 39884444351](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351): native / windows-11-arm / arm64 (failure). Steps: Packaged window, sandboxed bridge, and local client.
- [Run 39905111700](https://github.com/Perseusxrltd/mnemion/actions/runs/39905111700): verify (failure). Steps: Scan the exact downloaded distributions before publication.
