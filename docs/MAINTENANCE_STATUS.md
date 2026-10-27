# Automated maintenance status

Observed: 2026-10-27T02:53:05+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.34](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.34). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40440920428](https://github.com/Perseusxrltd/mnemion/actions/runs/40440920428) |
| public-updates\.yml | v4\.46\.34 | success | [Run 40439538705](https://github.com/Perseusxrltd/mnemion/actions/runs/40439538705) |
| release\.yml | release/4\.46\.34 | success | [Run 40433580410](https://github.com/Perseusxrltd/mnemion/actions/runs/40433580410) |
| release\.yml | release/4\.46\.35 | in\_progress | [Run 40439256250](https://github.com/Perseusxrltd/mnemion/actions/runs/40439256250) |
| verify-artifacts\.yml | main | success | [Run 40438996406](https://github.com/Perseusxrltd/mnemion/actions/runs/40438996406) |
| website-release\.yml | main | success | [Run 40440920343](https://github.com/Perseusxrltd/mnemion/actions/runs/40440920343) |
| website-release\.yml | v4\.46\.34 | success | [Run 40439536199](https://github.com/Perseusxrltd/mnemion/actions/runs/40439536199) |

## Active jobs

[Run 40440920428](https://github.com/Perseusxrltd/mnemion/actions/runs/40440920428): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/frontend run test:telemetry.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- container \(ubuntu-22\.04\): in\_progress.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.13\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40439256250](https://github.com/Perseusxrltd/mnemion/actions/runs/40439256250): 15/21 jobs completed; 14 succeeded.

- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.

