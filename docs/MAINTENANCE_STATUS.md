# Automated maintenance status

Observed: 2026-10-22T23:39:18+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.45.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.45.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39873108609](https://github.com/Perseusxrltd/mnemion/actions/runs/39873108609) |
| public-updates\.yml | v4\.45\.0 | success | [Run 39843181077](https://github.com/Perseusxrltd/mnemion/actions/runs/39843181077) |
| release\.yml | release/4\.45\.0 | success | [Run 39829833717](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717) |
| release\.yml | release/4\.45\.1 | failure | [Run 39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596) |
| release\.yml | release/4\.45\.1-r2 | success | [Run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559) |
| verify-artifacts\.yml | main | failure | [Run 39872601355](https://github.com/Perseusxrltd/mnemion/actions/runs/39872601355) |
| website-release\.yml | main | success | [Run 39873108664](https://github.com/Perseusxrltd/mnemion/actions/runs/39873108664) |
| website-release\.yml | v4\.45\.0 | success | [Run 39843176416](https://github.com/Perseusxrltd/mnemion/actions/runs/39843176416) |

## Active jobs

[Run 39873108609](https://github.com/Perseusxrltd/mnemion/actions/runs/39873108609): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Verify wheel and source package include the matching web Studio.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- container \(ubuntu-22\.04-arm\): in\_progress.
- container \(ubuntu-22\.04\): in\_progress — Post Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.


## Unsuccessful jobs

- [Run 39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596): native / macos-15-intel / x64 (cancelled). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596): native / macos-15 / arm64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39872601355](https://github.com/Perseusxrltd/mnemion/actions/runs/39872601355): verify (failure). Steps: Scan the exact downloaded distributions before publication.
