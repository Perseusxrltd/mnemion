# Automated maintenance status

Observed: 2026-10-23T00:17:18+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | queued | [Run 39877138975](https://github.com/Perseusxrltd/mnemion/actions/runs/39877138975) |
| public-updates\.yml | v4\.45\.1 | in\_progress | [Run 39876903393](https://github.com/Perseusxrltd/mnemion/actions/runs/39876903393) |
| release\.yml | release/4\.45\.1-r2 | success | [Run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559) |
| verify-artifacts\.yml | main | failure | [Run 39872601355](https://github.com/Perseusxrltd/mnemion/actions/runs/39872601355) |
| website-release\.yml | main | success | [Run 39877139000](https://github.com/Perseusxrltd/mnemion/actions/runs/39877139000) |
| website-release\.yml | v4\.45\.1 | success | [Run 39876908629](https://github.com/Perseusxrltd/mnemion/actions/runs/39876908629) |

## Active jobs

[Run 39877138975](https://github.com/Perseusxrltd/mnemion/actions/runs/39877138975): 1/12 jobs completed; 1 succeeded.

- lint: in\_progress — Scan exact source with pinned rules and an archived-key rejection control.
- studio: in\_progress — Check the lightweight native client before six-platform packaging.
- legacy: queued.
- container \(ubuntu-22\.04-arm\): queued.
- service \(3\.13\): queued.
- service \(3\.12\): in\_progress.
- supervision \(macos-15-intel\): queued.
- dependency-audit: in\_progress.
- service \(3\.14\): queued.
- supervision \(macos-15\): queued.
- container \(ubuntu-22\.04\): queued.

[Run 39876903393](https://github.com/Perseusxrltd/mnemion/actions/runs/39876903393): 1/7 jobs completed; 1 succeeded.

- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.


## Unsuccessful jobs

- [Run 39872601355](https://github.com/Perseusxrltd/mnemion/actions/runs/39872601355): verify (failure). Steps: Scan the exact downloaded distributions before publication.
