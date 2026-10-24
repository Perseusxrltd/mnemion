# Automated maintenance status

Observed: 2026-10-24T06:11:55+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.6](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.6). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40069186976](https://github.com/Perseusxrltd/mnemion/actions/runs/40069186976) |
| public-updates\.yml | v4\.46\.6 | success | [Run 40052003118](https://github.com/Perseusxrltd/mnemion/actions/runs/40052003118) |
| release\.yml | release/4\.46\.6 | success | [Run 40047223740](https://github.com/Perseusxrltd/mnemion/actions/runs/40047223740) |
| verify-artifacts\.yml | main | success | [Run 40051560833](https://github.com/Perseusxrltd/mnemion/actions/runs/40051560833) |
| website-release\.yml | main | success | [Run 40069186913](https://github.com/Perseusxrltd/mnemion/actions/runs/40069186913) |
| website-release\.yml | v4\.46\.6 | success | [Run 40052000728](https://github.com/Perseusxrltd/mnemion/actions/runs/40052000728) |

## Active jobs

[Run 40069186976](https://github.com/Perseusxrltd/mnemion/actions/runs/40069186976): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.12\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.

