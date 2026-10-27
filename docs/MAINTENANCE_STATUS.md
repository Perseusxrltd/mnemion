# Automated maintenance status

Observed: 2026-10-27T05:34:41+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.35](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.35). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 40456069954](https://github.com/Perseusxrltd/mnemion/actions/runs/40456069954) |
| public-updates\.yml | v4\.46\.35 | success | [Run 40444975984](https://github.com/Perseusxrltd/mnemion/actions/runs/40444975984) |
| release\.yml | release/4\.46\.35 | success | [Run 40439256250](https://github.com/Perseusxrltd/mnemion/actions/runs/40439256250) |
| release\.yml | release/4\.46\.36 | in\_progress | [Run 40451445143](https://github.com/Perseusxrltd/mnemion/actions/runs/40451445143) |
| verify-artifacts\.yml | main | success | [Run 40444539230](https://github.com/Perseusxrltd/mnemion/actions/runs/40444539230) |
| website-release\.yml | main | in\_progress | [Run 40456069956](https://github.com/Perseusxrltd/mnemion/actions/runs/40456069956) |
| website-release\.yml | v4\.46\.35 | success | [Run 40444972712](https://github.com/Perseusxrltd/mnemion/actions/runs/40444972712) |

## Active jobs

[Run 40456069954](https://github.com/Perseusxrltd/mnemion/actions/runs/40456069954): 2/12 jobs completed; 2 succeeded.

- studio: in\_progress — Check the lightweight native client before six-platform packaging.
- legacy: in\_progress — Run python -m pip install uv==0\.12\.24.
- dependency-audit: in\_progress — Run python -m pip install uv==0\.12\.24.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.14\): in\_progress — Initialize containers.
- service \(3\.12\): in\_progress — Initialize containers.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15\): in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- service \(3\.13\): in\_progress — Initialize containers.
- supervision \(macos-15-intel\): in\_progress — Set up job.

[Run 40451445143](https://github.com/Perseusxrltd/mnemion/actions/runs/40451445143): 21/22 jobs completed; 20 succeeded.

- assemble: in\_progress — Prepare or refresh the reviewable release draft.

