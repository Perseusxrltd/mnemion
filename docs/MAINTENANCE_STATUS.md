# Automated maintenance status

Observed: 2026-10-22T19:48:05+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | pending | [Run 39843078723](https://github.com/Perseusxrltd/mnemion/actions/runs/39843078723) |
| public-updates\.yml | v4\.45\.0 | queued | [Run 39843181077](https://github.com/Perseusxrltd/mnemion/actions/runs/39843181077) |
| release\.yml | release/4\.45\.0 | success | [Run 39829833717](https://github.com/Perseusxrltd/mnemion/actions/runs/39829833717) |
| verify-artifacts\.yml | main | in\_progress | [Run 39840069973](https://github.com/Perseusxrltd/mnemion/actions/runs/39840069973) |
| website-release\.yml | v4\.45\.0 | success | [Run 39843176416](https://github.com/Perseusxrltd/mnemion/actions/runs/39843176416) |

## Active jobs

[Run 39843078723](https://github.com/Perseusxrltd/mnemion/actions/runs/39843078723): 0/2 jobs completed; 0 succeeded.

- Select checks: queued.
- lint: queued.

[Run 39843181077](https://github.com/Perseusxrltd/mnemion/actions/runs/39843181077): 1/7 jobs completed; 1 succeeded.

- windows / x64 public upgrade: in\_progress — Run python -m pip install psutil==7\.2\.2.
- linux / x64 public upgrade: in\_progress — Linux desktop libraries.
- macos / arm64 public upgrade: queued.
- windows / arm64 public upgrade: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- linux / arm64 public upgrade: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- macos / x64 public upgrade: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.

