# Automated maintenance status

Observed: 2026-10-29T04:59:39+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.49](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.49). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | success | [Run 40820612659](https://github.com/Perseusxrltd/mnemion/actions/runs/40820612659) |
| public-updates\.yml | v4\.46\.49 | in\_progress | [Run 40820128156](https://github.com/Perseusxrltd/mnemion/actions/runs/40820128156) |
| release\.yml | release/4\.46\.49 | success | [Run 40812422400](https://github.com/Perseusxrltd/mnemion/actions/runs/40812422400) |
| release\.yml | release/4\.46\.50 | in\_progress | [Run 40815491489](https://github.com/Perseusxrltd/mnemion/actions/runs/40815491489) |
| verify-artifacts\.yml | main | success | [Run 40819658418](https://github.com/Perseusxrltd/mnemion/actions/runs/40819658418) |
| website-release\.yml | main | success | [Run 40820612636](https://github.com/Perseusxrltd/mnemion/actions/runs/40820612636) |
| website-release\.yml | v4\.46\.49 | success | [Run 40820125119](https://github.com/Perseusxrltd/mnemion/actions/runs/40820125119) |

## Active jobs

[Run 40820128156](https://github.com/Perseusxrltd/mnemion/actions/runs/40820128156): 4/7 jobs completed; 4 succeeded.

- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 40815491489](https://github.com/Perseusxrltd/mnemion/actions/runs/40815491489): 13/14 jobs completed; 12 succeeded.

- native / native\_database / Database / windows / x64: in\_progress — Compile pinned PostgreSQL, vector extension and static libraries.

