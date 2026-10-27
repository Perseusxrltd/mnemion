# Automated maintenance status

Observed: 2026-10-27T15:14:10+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.40](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.40). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | codex/telemetry-sql-reads-20261027 | in\_progress | [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882) |
| ci\.yml | main | queued | [Run 40524093039](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039) |
| public-updates\.yml | v4\.46\.40 | queued | [Run 40528686080](https://github.com/Perseusxrltd/mnemion/actions/runs/40528686080) |
| release\.yml | release/4\.46\.40 | success | [Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119) |
| release\.yml | release/4\.46\.41 | queued | [Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699) |
| verify-artifacts\.yml | main | success | [Run 40527649322](https://github.com/Perseusxrltd/mnemion/actions/runs/40527649322) |
| website-release\.yml | main | success | [Run 40513098255](https://github.com/Perseusxrltd/mnemion/actions/runs/40513098255) |
| website-release\.yml | v4\.46\.40 | success | [Run 40528680423](https://github.com/Perseusxrltd/mnemion/actions/runs/40528680423) |

## Active jobs

[Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882): 11/12 jobs completed; 10 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40524093039](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039): 11/12 jobs completed; 11 succeeded.

- supervision \(macos-15\): queued.

[Run 40528686080](https://github.com/Perseusxrltd/mnemion/actions/runs/40528686080): 1/7 jobs completed; 1 succeeded.

- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: queued.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699): 13/14 jobs completed; 12 succeeded.

- native / native\_database / Database / macos / arm64: queued.


## Unsuccessful jobs

- [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882): supervision \(macos-15\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
