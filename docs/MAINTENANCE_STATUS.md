# Automated maintenance status

Observed: 2026-10-23T20:50:45+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.5](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.5). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40009317328](https://github.com/Perseusxrltd/mnemion/actions/runs/40009317328) |
| public-updates\.yml | v4\.46\.5 | in\_progress | [Run 40022243634](https://github.com/Perseusxrltd/mnemion/actions/runs/40022243634) |
| release\.yml | release/4\.46\.5-r2 | success | [Run 40013991029](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029) |
| verify-artifacts\.yml | main | success | [Run 40021524126](https://github.com/Perseusxrltd/mnemion/actions/runs/40021524126) |
| website-release\.yml | main | success | [Run 40009317318](https://github.com/Perseusxrltd/mnemion/actions/runs/40009317318) |
| website-release\.yml | v4\.46\.5 | success | [Run 40022240433](https://github.com/Perseusxrltd/mnemion/actions/runs/40022240433) |

## Active jobs

[Run 40022243634](https://github.com/Perseusxrltd/mnemion/actions/runs/40022243634): 1/7 jobs completed; 1 succeeded.

- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.

