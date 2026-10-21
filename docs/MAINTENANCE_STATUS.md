# Automated maintenance status

Observed: 2026-10-21T01:56:38+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | queued | [Run 39530171334](https://github.com/Perseusxrltd/mnemion/actions/runs/39530171334) |
| public-updates\.yml | v4\.43\.0 | success | [Run 39518522368](https://github.com/Perseusxrltd/mnemion/actions/runs/39518522368) |
| release\.yml | release/4\.43\.0 | success | [Run 39460885775](https://github.com/Perseusxrltd/mnemion/actions/runs/39460885775) |
| verify-artifacts\.yml | main | success | [Run 39518325759](https://github.com/Perseusxrltd/mnemion/actions/runs/39518325759) |
| website-release\.yml | main | in\_progress | [Run 39530171313](https://github.com/Perseusxrltd/mnemion/actions/runs/39530171313) |
| website-release\.yml | v4\.43\.0 | success | [Run 39518520187](https://github.com/Perseusxrltd/mnemion/actions/runs/39518520187) |

## Active jobs

[Run 39530171334](https://github.com/Perseusxrltd/mnemion/actions/runs/39530171334): 2/12 jobs completed; 2 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- supervision \(macos-15\): queued.
- container \(ubuntu-22\.04\): in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- service \(3\.13\): in\_progress — Set up job.
- legacy: in\_progress.
- container \(ubuntu-22\.04-arm\): queued.
- supervision \(macos-15-intel\): in\_progress.
- service \(3\.14\): in\_progress.
- dependency-audit: in\_progress.
- service \(3\.12\): in\_progress.

