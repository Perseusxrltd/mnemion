# Automated maintenance status

Observed: 2026-10-23T18:10:43+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.3](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.3). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40001037372](https://github.com/Perseusxrltd/mnemion/actions/runs/40001037372) |
| public-updates\.yml | v4\.46\.3 | success | [Run 39973022163](https://github.com/Perseusxrltd/mnemion/actions/runs/39973022163) |
| release\.yml | release/4\.46\.3 | success | [Run 39961881757](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757) |
| release\.yml | release/4\.46\.4 | in\_progress | [Run 39997298864](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864) |
| verify-artifacts\.yml | main | success | [Run 39972316494](https://github.com/Perseusxrltd/mnemion/actions/runs/39972316494) |
| website-release\.yml | main | success | [Run 40001037360](https://github.com/Perseusxrltd/mnemion/actions/runs/40001037360) |
| website-release\.yml | v4\.46\.3 | success | [Run 39973017198](https://github.com/Perseusxrltd/mnemion/actions/runs/39973017198) |

## Active jobs

[Run 40001037372](https://github.com/Perseusxrltd/mnemion/actions/runs/40001037372): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron ci && npm --prefix studio/electron test.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.12\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.13\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.

[Run 39997298864](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864): 19/21 jobs completed; 18 succeeded.

- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.

