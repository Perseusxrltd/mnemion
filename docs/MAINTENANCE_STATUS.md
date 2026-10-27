# Automated maintenance status

Observed: 2026-10-27T02:07:53+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.29](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.29). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40433638960](https://github.com/Perseusxrltd/mnemion/actions/runs/40433638960) |
| public-updates\.yml | v4\.46\.29 | success | [Run 40423899386](https://github.com/Perseusxrltd/mnemion/actions/runs/40423899386) |
| release\.yml | release/4\.46\.29 | success | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| release\.yml | release/4\.46\.33 | failure | [Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624) |
| release\.yml | release/4\.46\.34 | in\_progress | [Run 40433580410](https://github.com/Perseusxrltd/mnemion/actions/runs/40433580410) |
| verify-artifacts\.yml | main | skipped | [Run 40430456976](https://github.com/Perseusxrltd/mnemion/actions/runs/40430456976) |
| website-release\.yml | main | success | [Run 40433638922](https://github.com/Perseusxrltd/mnemion/actions/runs/40433638922) |
| website-release\.yml | v4\.46\.29 | success | [Run 40423894613](https://github.com/Perseusxrltd/mnemion/actions/runs/40423894613) |

## Active jobs

[Run 40433580410](https://github.com/Perseusxrltd/mnemion/actions/runs/40433580410): 19/21 jobs completed; 18 succeeded.

- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.


## Unsuccessful jobs

- [Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624): native / windows-2022 / x64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
