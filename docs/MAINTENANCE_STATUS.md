# Automated maintenance status

Observed: 2026-10-26T19:18:55+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.22](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.22). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 40385484447](https://github.com/Perseusxrltd/mnemion/actions/runs/40385484447) |
| public-updates\.yml | v4\.46\.22 | success | [Run 40366545289](https://github.com/Perseusxrltd/mnemion/actions/runs/40366545289) |
| release\.yml | release/4\.46\.22 | success | [Run 40351425614](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614) |
| release\.yml | release/4\.46\.24 | failure | [Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179) |
| release\.yml | release/4\.46\.25 | in\_progress | [Run 40376743057](https://github.com/Perseusxrltd/mnemion/actions/runs/40376743057) |
| release\.yml | release/4\.46\.26 | pending | [Run 40384317169](https://github.com/Perseusxrltd/mnemion/actions/runs/40384317169) |
| verify-artifacts\.yml | main | skipped | [Run 40380652346](https://github.com/Perseusxrltd/mnemion/actions/runs/40380652346) |
| website-release\.yml | main | success | [Run 40385484524](https://github.com/Perseusxrltd/mnemion/actions/runs/40385484524) |
| website-release\.yml | v4\.46\.22 | success | [Run 40366540445](https://github.com/Perseusxrltd/mnemion/actions/runs/40366540445) |

## Active jobs

[Run 40385484447](https://github.com/Perseusxrltd/mnemion/actions/runs/40385484447): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/frontend run test:telemetry.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): queued.
- container \(ubuntu-22\.04\): in\_progress — Verify the non-root image includes Studio, guides and notices offline.
- service \(3\.12\): in\_progress — Run uv sync --locked --python 3\.12 --group dev.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.13\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.

[Run 40376743057](https://github.com/Perseusxrltd/mnemion/actions/runs/40376743057): 18/21 jobs completed; 16 succeeded.

- native / macos-15 / arm64: in\_progress — Packaged Mac update, restart guards and relaunch.
- native / windows-2022 / x64: in\_progress — Native Windows installation, authenticated upgrade and relaunch.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179): native / ubuntu-22\.04 / x64 (failure). Steps: Package the native desktop with one bounded upstream-download retry.
- [Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179): native / ubuntu-22\.04-arm / arm64 (failure). Steps: Package the native desktop with one bounded upstream-download retry.
- [Run 40376743057](https://github.com/Perseusxrltd/mnemion/actions/runs/40376743057): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
