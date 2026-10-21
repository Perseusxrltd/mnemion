# Automated maintenance status

Observed: 2026-10-21T01:28:52+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.43.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.43.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39527490005](https://github.com/Perseusxrltd/mnemion/actions/runs/39527490005) |
| public-updates\.yml | v4\.43\.0 | success | [Run 39518522368](https://github.com/Perseusxrltd/mnemion/actions/runs/39518522368) |
| release\.yml | release/4\.43\.0 | success | [Run 39460885775](https://github.com/Perseusxrltd/mnemion/actions/runs/39460885775) |
| verify-artifacts\.yml | main | success | [Run 39518325759](https://github.com/Perseusxrltd/mnemion/actions/runs/39518325759) |
| website-release\.yml | main | success | [Run 39527490010](https://github.com/Perseusxrltd/mnemion/actions/runs/39527490010) |
| website-release\.yml | v4\.43\.0 | success | [Run 39518520187](https://github.com/Perseusxrltd/mnemion/actions/runs/39518520187) |

## Active jobs

[Run 39527490005](https://github.com/Perseusxrltd/mnemion/actions/runs/39527490005): 3/12 jobs completed; 2 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron ci && npm --prefix studio/electron test.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- container \(ubuntu-22\.04\): in\_progress — Complete job.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.13\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.


## Unsuccessful jobs

- [Run 39527490005](https://github.com/Perseusxrltd/mnemion/actions/runs/39527490005): dependency-audit (failure). Steps: Run uvx pip-audit --path \.venv/lib/python3\.12/site-packages.
