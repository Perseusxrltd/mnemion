# Automated maintenance status

Observed: 2026-10-23T05:46:22+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 39907532985](https://github.com/Perseusxrltd/mnemion/actions/runs/39907532985) |
| public-updates\.yml | v4\.46\.0 | in\_progress | [Run 39907316827](https://github.com/Perseusxrltd/mnemion/actions/runs/39907316827) |
| release\.yml | release/4\.46\.0-r2 | success | [Run 39895069093](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093) |
| verify-artifacts\.yml | main | failure | [Run 39901894314](https://github.com/Perseusxrltd/mnemion/actions/runs/39901894314) |
| website-release\.yml | main | success | [Run 39907532979](https://github.com/Perseusxrltd/mnemion/actions/runs/39907532979) |
| website-release\.yml | v4\.46\.0 | success | [Run 39907323013](https://github.com/Perseusxrltd/mnemion/actions/runs/39907323013) |

## Active jobs

[Run 39907532985](https://github.com/Perseusxrltd/mnemion/actions/runs/39907532985): 0/3 jobs completed; 0 succeeded.

- Select checks: in\_progress — Set up job.
- studio: in\_progress.
- lint: queued.

[Run 39907316827](https://github.com/Perseusxrltd/mnemion/actions/runs/39907316827): 1/7 jobs completed; 1 succeeded.

- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.


## Unsuccessful jobs

- [Run 39901894314](https://github.com/Perseusxrltd/mnemion/actions/runs/39901894314): verify (failure). Steps: Scan the exact downloaded distributions before publication.
