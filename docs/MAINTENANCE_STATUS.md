# Automated maintenance status

Observed: 2026-10-23T14:44:28+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.2](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.2). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 39972086704](https://github.com/Perseusxrltd/mnemion/actions/runs/39972086704) |
| public-updates\.yml | v4\.46\.2 | success | [Run 39952552845](https://github.com/Perseusxrltd/mnemion/actions/runs/39952552845) |
| release\.yml | release/4\.46\.2 | success | [Run 39945380878](https://github.com/Perseusxrltd/mnemion/actions/runs/39945380878) |
| release\.yml | release/4\.46\.3 | in\_progress | [Run 39961881757](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757) |
| verify-artifacts\.yml | main | skipped | [Run 39964156899](https://github.com/Perseusxrltd/mnemion/actions/runs/39964156899) |
| website-release\.yml | main | success | [Run 39972087030](https://github.com/Perseusxrltd/mnemion/actions/runs/39972087030) |
| website-release\.yml | v4\.46\.2 | success | [Run 39952548379](https://github.com/Perseusxrltd/mnemion/actions/runs/39952548379) |

## Active jobs

[Run 39972086704](https://github.com/Perseusxrltd/mnemion/actions/runs/39972086704): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix packages/client test.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- container \(ubuntu-22\.04\): in\_progress — Post Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15\): queued.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.

[Run 39961881757](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757): 21/22 jobs completed; 20 succeeded.

- assemble: in\_progress — Prepare or refresh the reviewable release draft.

