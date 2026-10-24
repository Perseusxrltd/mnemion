# Automated maintenance status

Observed: 2026-10-24T00:52:44+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | queued | [Run 40047066725](https://github.com/Perseusxrltd/mnemion/actions/runs/40047066725) |
| public-updates\.yml | v4\.46\.5 | success | [Run 40022243634](https://github.com/Perseusxrltd/mnemion/actions/runs/40022243634) |
| release\.yml | release/4\.46\.5-r2 | success | [Run 40013991029](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029) |
| verify-artifacts\.yml | main | success | [Run 40021524126](https://github.com/Perseusxrltd/mnemion/actions/runs/40021524126) |
| website-release\.yml | main | success | [Run 40047066746](https://github.com/Perseusxrltd/mnemion/actions/runs/40047066746) |
| website-release\.yml | v4\.46\.5 | success | [Run 40022240433](https://github.com/Perseusxrltd/mnemion/actions/runs/40022240433) |

## Active jobs

[Run 40047066725](https://github.com/Perseusxrltd/mnemion/actions/runs/40047066725): 1/12 jobs completed; 1 succeeded.

- lint: in\_progress — Run uv sync --locked --group dev.
- studio: in\_progress — Check the lightweight native client before six-platform packaging.
- legacy: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- supervision \(macos-15\): in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- service \(3\.12\): in\_progress — Initialize containers.
- supervision \(macos-15-intel\): in\_progress — Set up job.
- service \(3\.13\): in\_progress — Initialize containers.
- dependency-audit: in\_progress — Run python -m pip install uv==0\.12\.24.
- service \(3\.14\): in\_progress — Initialize containers.
- container \(ubuntu-22\.04-arm\): in\_progress — Set up job.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.

