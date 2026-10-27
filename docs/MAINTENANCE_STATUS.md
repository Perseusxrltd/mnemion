# Automated maintenance status

Observed: 2026-10-27T15:06:51+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.39](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.39). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | codex/telemetry-sql-reads-20261027 | in\_progress | [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882) |
| ci\.yml | main | in\_progress | [Run 40524093039](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039) |
| public-updates\.yml | v4\.46\.39 | success | [Run 40521216857](https://github.com/Perseusxrltd/mnemion/actions/runs/40521216857) |
| release\.yml | release/4\.46\.39 | success | [Run 40504681891](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891) |
| release\.yml | release/4\.46\.40 | success | [Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119) |
| release\.yml | release/4\.46\.41 | queued | [Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699) |
| verify-artifacts\.yml | main | in\_progress | [Run 40527649322](https://github.com/Perseusxrltd/mnemion/actions/runs/40527649322) |
| website-release\.yml | main | success | [Run 40524092744](https://github.com/Perseusxrltd/mnemion/actions/runs/40524092744) |
| website-release\.yml | v4\.46\.39 | success | [Run 40521210268](https://github.com/Perseusxrltd/mnemion/actions/runs/40521210268) |

## Active jobs

[Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882): 10/12 jobs completed; 9 succeeded.

- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40524093039](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039): 11/12 jobs completed; 10 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699): 3/8 jobs completed; 2 succeeded.

- Reuse verified Product checks: in\_progress — Run actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02.
- native / Encrypted files / Windows / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / Encrypted files / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Private state / Windows / arm64: in\_progress — Set up job.
- native / native\_database / Private state / Windows / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.

[Run 40527649322](https://github.com/Perseusxrltd/mnemion/actions/runs/40527649322): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.


## Unsuccessful jobs

- [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882): supervision \(macos-15\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40524093039](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039): supervision \(macos-15\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
