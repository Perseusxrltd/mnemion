# Automated maintenance status

Observed: 2026-10-23T12:04:36+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.1](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.1). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39947061896](https://github.com/Perseusxrltd/mnemion/actions/runs/39947061896) |
| database-cache\.yml | main | success | [Run 39931143679](https://github.com/Perseusxrltd/mnemion/actions/runs/39931143679) |
| public-updates\.yml | v4\.46\.1 | success | [Run 39925663475](https://github.com/Perseusxrltd/mnemion/actions/runs/39925663475) |
| release\.yml | release/4\.46\.1-r2 | success | [Run 39916372505](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505) |
| release\.yml | release/4\.46\.2 | in\_progress | [Run 39945380878](https://github.com/Perseusxrltd/mnemion/actions/runs/39945380878) |
| verify-artifacts\.yml | main | success | [Run 39925023152](https://github.com/Perseusxrltd/mnemion/actions/runs/39925023152) |
| website-release\.yml | main | success | [Run 39950527337](https://github.com/Perseusxrltd/mnemion/actions/runs/39950527337) |
| website-release\.yml | v4\.46\.1 | success | [Run 39925659880](https://github.com/Perseusxrltd/mnemion/actions/runs/39925659880) |

## Active jobs

[Run 39947061896](https://github.com/Perseusxrltd/mnemion/actions/runs/39947061896): 11/12 jobs completed; 11 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39945380878](https://github.com/Perseusxrltd/mnemion/actions/runs/39945380878): 30/32 jobs completed; 29 succeeded.

- native / windows-11-arm / arm64: in\_progress — Native Windows installation, authenticated upgrade and relaunch.
- native / macos-15-intel / x64: in\_progress — Run actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02.

