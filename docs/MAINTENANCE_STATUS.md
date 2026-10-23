# Automated maintenance status

Observed: 2026-10-23T02:48:25+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | in\_progress | [Run 39891502379](https://github.com/Perseusxrltd/mnemion/actions/runs/39891502379) |
| public-updates\.yml | v4\.45\.1 | success | [Run 39876903393](https://github.com/Perseusxrltd/mnemion/actions/runs/39876903393) |
| release\.yml | release/4\.45\.1-r2 | success | [Run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559) |
| release\.yml | release/4\.46\.0 | failure | [Run 39884444351](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351) |
| verify-artifacts\.yml | main | skipped | [Run 39891242926](https://github.com/Perseusxrltd/mnemion/actions/runs/39891242926) |
| website-release\.yml | main | success | [Run 39891502377](https://github.com/Perseusxrltd/mnemion/actions/runs/39891502377) |
| website-release\.yml | v4\.45\.1 | success | [Run 39876908629](https://github.com/Perseusxrltd/mnemion/actions/runs/39876908629) |

## Active jobs

[Run 39891502379](https://github.com/Perseusxrltd/mnemion/actions/runs/39891502379): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Verify wheel and source package include the matching web Studio.
- service \(3\.14\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.


## Unsuccessful jobs

- [Run 39884444351](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351): native / windows-2022 / x64 (failure). Steps: Packaged window, sandboxed bridge, and local client.
- [Run 39884444351](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351): native / windows-11-arm / arm64 (failure). Steps: Packaged window, sandboxed bridge, and local client.
