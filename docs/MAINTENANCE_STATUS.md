# Automated maintenance status

Observed: 2026-10-22T19:48:50+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | in\_progress | [Run 39843078723](https://github.com/Perseusxrltd/mnemion/actions/runs/39843078723) |
| public-updates\.yml | v4\.45\.0 | queued | [Run 39843181077](https://github.com/Perseusxrltd/mnemion/actions/runs/39843181077) |
| release\.yml | release/4\.45\.0 | success | [Run 39829833717](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717) |
| verify-artifacts\.yml | main | in\_progress | [Run 39840069973](https://github.com/Perseusxrltd/mnemion/actions/runs/39840069973) |
| website-release\.yml | v4\.45\.0 | success | [Run 39843176416](https://github.com/Perseusxrltd/mnemion/actions/runs/39843176416) |

## Active jobs

[Run 39843078723](https://github.com/Perseusxrltd/mnemion/actions/runs/39843078723): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.

[Run 39843181077](https://github.com/Perseusxrltd/mnemion/actions/runs/39843181077): 1/7 jobs completed; 1 succeeded.

- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Linux desktop libraries.
- macos / arm64 public upgrade: queued.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.

