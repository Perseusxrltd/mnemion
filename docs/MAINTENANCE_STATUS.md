# Automated maintenance status

Observed: 2026-10-21T00:00:17+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | success | [Run 39460842888](https://github.com/Perseusxrltd/mnemion/actions/runs/39460842888) |
| public-updates\.yml | v4\.43\.0 | in\_progress | [Run 39518522368](https://github.com/Perseusxrltd/mnemion/actions/runs/39518522368) |
| release\.yml | release/4\.43\.0 | success | [Run 39460885775](https://github.com/Perseusxrltd/mnemion/actions/runs/39460885775) |
| verify-artifacts\.yml | main | success | [Run 39518325759](https://github.com/Perseusxrltd/mnemion/actions/runs/39518325759) |
| website-release\.yml | main | success | [Run 39460842819](https://github.com/Perseusxrltd/mnemion/actions/runs/39460842819) |
| website-release\.yml | v4\.43\.0 | success | [Run 39518520187](https://github.com/Perseusxrltd/mnemion/actions/runs/39518520187) |

## Active jobs

[Run 39518522368](https://github.com/Perseusxrltd/mnemion/actions/runs/39518522368): 1/7 jobs completed; 1 succeeded.

- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- linux / x64 public upgrade: in\_progress — Linux desktop libraries.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.

