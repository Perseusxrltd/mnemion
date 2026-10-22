# Automated maintenance status

Observed: 2026-10-22T22:32:57+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | in\_progress | [Run 39865654240](https://github.com/Perseusxrltd/mnemion/actions/runs/39865654240) |
| public-updates\.yml | v4\.45\.0 | success | [Run 39843181077](https://github.com/Perseusxrltd/mnemion/actions/runs/39843181077) |
| release\.yml | release/4\.45\.0 | success | [Run 39829833717](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717) |
| release\.yml | release/4\.45\.1 | failure | [Run 39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596) |
| release\.yml | release/4\.45\.1-r2 | in\_progress | [Run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559) |
| verify-artifacts\.yml | main | skipped | [Run 39864403901](https://github.com/Perseusxrltd/mnemion/actions/runs/39864403901) |
| website-release\.yml | main | success | [Run 39865654359](https://github.com/Perseusxrltd/mnemion/actions/runs/39865654359) |
| website-release\.yml | v4\.45\.0 | success | [Run 39843176416](https://github.com/Perseusxrltd/mnemion/actions/runs/39843176416) |

## Active jobs

[Run 39865654240](https://github.com/Perseusxrltd/mnemion/actions/runs/39865654240): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron ci && npm --prefix studio/electron test.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04-arm\): in\_progress — Post Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- service \(3\.13\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- container \(ubuntu-22\.04\): in\_progress — Post Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.

[Run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559): 15/21 jobs completed; 14 succeeded.

- native / ubuntu-22\.04 / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.


## Unsuccessful jobs

- [Run 39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596): native / macos-15-intel / x64 (cancelled). Steps: Installed app creates, searches and reopens a real local workspace.
- [Run 39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596): native / macos-15 / arm64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
