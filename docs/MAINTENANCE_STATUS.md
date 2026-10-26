# Automated maintenance status

Observed: 2026-10-26T23:48:05+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.28](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.28). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40416515726](https://github.com/Perseusxrltd/mnemion/actions/runs/40416515726) |
| public-updates\.yml | v4\.46\.28 | success | [Run 40411258731](https://github.com/Perseusxrltd/mnemion/actions/runs/40411258731) |
| release\.yml | release/4\.46\.28 | success | [Run 40399013490](https://github.com/Perseusxrltd/mnemion/actions/runs/40399013490) |
| release\.yml | release/4\.46\.29 | success | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| release\.yml | release/4\.46\.30 | failure | [Run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100) |
| release\.yml | release/4\.46\.31 | cancelled | [Run 40417437026](https://github.com/Perseusxrltd/mnemion/actions/runs/40417437026) |
| verify-artifacts\.yml | main | skipped | [Run 40422136119](https://github.com/Perseusxrltd/mnemion/actions/runs/40422136119) |
| website-release\.yml | main | success | [Run 40416515248](https://github.com/Perseusxrltd/mnemion/actions/runs/40416515248) |
| website-release\.yml | v4\.46\.28 | success | [Run 40411254189](https://github.com/Perseusxrltd/mnemion/actions/runs/40411254189) |

## Unsuccessful jobs

- [Run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100): native / windows-2022 / x64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
