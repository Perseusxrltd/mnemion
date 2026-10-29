# Automated maintenance status

Observed: 2026-10-29T02:41:41+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.46](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.46). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#47](https://github.com/Perseusxrltd/mnemion/issues/47) | Field report \(4\.46\.40\): multi-agent usage audit — slow/hanging search, suspended connector scope, noisy activity log, unusable vault over MCP, and features left unused | 2026-10-28T17:01:24Z |
| [#48](https://github.com/Perseusxrltd/mnemion/issues/48) | Mnemion as the single system: full replacement of LEDGER/DISPATCH/files, plus vault compatibility | 2026-10-28T09:04:09Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40802929823](https://github.com/Perseusxrltd/mnemion/actions/runs/40802929823) |
| public-updates\.yml | v4\.46\.46 | success | [Run 40801713765](https://github.com/Perseusxrltd/mnemion/actions/runs/40801713765) |
| release\.yml | release/4\.46\.46-r2 | success | [Run 40793646583](https://github.com/Perseusxrltd/mnemion/actions/runs/40793646583) |
| release\.yml | release/4\.46\.47 | success | [Run 40801649181](https://github.com/Perseusxrltd/mnemion/actions/runs/40801649181) |
| release\.yml | release/4\.46\.48 | in\_progress | [Run 40806507811](https://github.com/Perseusxrltd/mnemion/actions/runs/40806507811) |
| verify-artifacts\.yml | main | in\_progress | [Run 40807818311](https://github.com/Perseusxrltd/mnemion/actions/runs/40807818311) |
| website-release\.yml | main | success | [Run 40802930121](https://github.com/Perseusxrltd/mnemion/actions/runs/40802930121) |
| website-release\.yml | v4\.46\.46 | success | [Run 40801711006](https://github.com/Perseusxrltd/mnemion/actions/runs/40801711006) |

## Active jobs

[Run 40806507811](https://github.com/Perseusxrltd/mnemion/actions/runs/40806507811): 4/8 jobs completed; 3 succeeded.

- native / Encrypted files / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / Encrypted files / Windows / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Private state / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Private state / Windows / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.

[Run 40807818311](https://github.com/Perseusxrltd/mnemion/actions/runs/40807818311): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.

