# Automated maintenance status

Observed: 2026-10-26T16:17:31+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.19](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.19). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 40357519721](https://github.com/Perseusxrltd/mnemion/actions/runs/40357519721) |
| public-updates\.yml | v4\.46\.19 | success | [Run 40344852373](https://github.com/Perseusxrltd/mnemion/actions/runs/40344852373) |
| release\.yml | release/4\.46\.19 | success | [Run 40333990605](https://github.com/Perseusxrltd/mnemion/actions/runs/40333990605) |
| release\.yml | release/4\.46\.22 | in\_progress | [Run 40351425614](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614) |
| verify-artifacts\.yml | main | success | [Run 40343874190](https://github.com/Perseusxrltd/mnemion/actions/runs/40343874190) |
| website-release\.yml | main | success | [Run 40357519693](https://github.com/Perseusxrltd/mnemion/actions/runs/40357519693) |
| website-release\.yml | v4\.46\.19 | success | [Run 40344847819](https://github.com/Perseusxrltd/mnemion/actions/runs/40344847819) |

## Active jobs

[Run 40357519721](https://github.com/Perseusxrltd/mnemion/actions/runs/40357519721): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/frontend run test:telemetry.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15\): queued.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- container \(ubuntu-22\.04-arm\): in\_progress — Verify the non-root image includes Studio, guides and notices offline.
- container \(ubuntu-22\.04\): in\_progress.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.

[Run 40351425614](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614): 19/21 jobs completed; 17 succeeded.

- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 40351425614](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614): native / macos-15 / arm64 (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
