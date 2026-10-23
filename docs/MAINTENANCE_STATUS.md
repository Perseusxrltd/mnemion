# Automated maintenance status

Observed: 2026-10-23T06:46:00+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | queued | [Run 39913409273](https://github.com/Perseusxrltd/mnemion/actions/runs/39913409273) |
| public-updates\.yml | v4\.46\.0 | success | [Run 39907316827](https://github.com/Perseusxrltd/mnemion/actions/runs/39907316827) |
| release\.yml | release/4\.46\.0-r2 | success | [Run 39895069093](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093) |
| verify-artifacts\.yml | main | failure | [Run 39901894314](https://github.com/Perseusxrltd/mnemion/actions/runs/39901894314) |
| website-release\.yml | main | success | [Run 39913409255](https://github.com/Perseusxrltd/mnemion/actions/runs/39913409255) |
| website-release\.yml | v4\.46\.0 | success | [Run 39907323013](https://github.com/Perseusxrltd/mnemion/actions/runs/39907323013) |

## Active jobs

[Run 39913409273](https://github.com/Perseusxrltd/mnemion/actions/runs/39913409273): 2/12 jobs completed; 2 succeeded.

- studio: in\_progress — Check the lightweight native client before six-platform packaging.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- dependency-audit: in\_progress — Run uvx pip-audit --path \.venv/lib/python3\.12/site-packages.
- legacy: in\_progress — Run uv sync --locked --extra legacy --group dev.
- service \(3\.12\): in\_progress — Initialize containers.
- container \(ubuntu-22\.04-arm\): queued.
- supervision \(macos-15\): in\_progress — Install the native service without building on a managed host.
- service \(3\.13\): in\_progress — Initialize containers.
- service \(3\.14\): in\_progress — Initialize containers.


## Unsuccessful jobs

- [Run 39901894314](https://github.com/Perseusxrltd/mnemion/actions/runs/39901894314): verify (failure). Steps: Scan the exact downloaded distributions before publication.
