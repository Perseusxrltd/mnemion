# Automated maintenance status

Observed: 2026-10-27T17:25:18+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.40](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.40). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | codex/telemetry-sql-reads-20261027 | failure | [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882) |
| ci\.yml | main | success | [Run 40534190873](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190873) |
| database-cache\.yml | main | success | [Run 40534190892](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190892) |
| public-updates\.yml | v4\.46\.40 | failure | [Run 40528686080](https://github.com/Perseusxrltd/mnemion/actions/runs/40528686080) |
| release\.yml | release/4\.46\.40 | success | [Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119) |
| release\.yml | release/4\.46\.41 | failure | [Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699) |
| release\.yml | release/4\.46\.42 | success | [Run 40540729543](https://github.com/Perseusxrltd/mnemion/actions/runs/40540729543) |
| verify-artifacts\.yml | main | in\_progress | [Run 40550326047](https://github.com/Perseusxrltd/mnemion/actions/runs/40550326047) |
| website-release\.yml | main | success | [Run 40534190911](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190911) |
| website-release\.yml | v4\.46\.40 | success | [Run 40528680423](https://github.com/Perseusxrltd/mnemion/actions/runs/40528680423) |

## Active jobs

[Run 40550326047](https://github.com/Perseusxrltd/mnemion/actions/runs/40550326047): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.


## Unsuccessful jobs

- [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882): supervision \(macos-15\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40528686080](https://github.com/Perseusxrltd/mnemion/actions/runs/40528686080): macos / arm64 public upgrade (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699): native / native\_database / Database / macos / arm64 (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
