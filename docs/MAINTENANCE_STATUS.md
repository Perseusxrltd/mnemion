# Automated maintenance status

Observed: 2026-10-27T01:01:10+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.29](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.29). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 40430021395](https://github.com/Perseusxrltd/mnemion/actions/runs/40430021395) |
| public-updates\.yml | v4\.46\.29 | success | [Run 40423899386](https://github.com/Perseusxrltd/mnemion/actions/runs/40423899386) |
| release\.yml | release/4\.46\.29 | success | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| release\.yml | release/4\.46\.33 | in\_progress | [Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624) |
| verify-artifacts\.yml | main | failure | [Run 40417189624](https://github.com/Perseusxrltd/mnemion/actions/runs/40417189624) |
| website-release\.yml | main | queued | [Run 40430021427](https://github.com/Perseusxrltd/mnemion/actions/runs/40430021427) |
| website-release\.yml | v4\.46\.29 | success | [Run 40423894613](https://github.com/Perseusxrltd/mnemion/actions/runs/40423894613) |

## Active jobs

[Run 40430021395](https://github.com/Perseusxrltd/mnemion/actions/runs/40430021395): 0/3 jobs completed; 0 succeeded.

- studio: in\_progress — Set up job.
- lint: queued.
- Select checks: in\_progress.

[Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624): 20/21 jobs completed; 17 succeeded.

- native / macos-15-intel / x64: in\_progress — Packaged Mac update, restart guards and relaunch.

[Run 40430021427](https://github.com/Perseusxrltd/mnemion/actions/runs/40430021427): 0/1 jobs completed; 0 succeeded.

- synchronize: in\_progress — Set up job.


## Unsuccessful jobs

- [Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624): native / windows-2022 / x64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40417189624](https://github.com/Perseusxrltd/mnemion/actions/runs/40417189624): verify (failure). Steps: Scan the exact downloaded distributions before publication.
