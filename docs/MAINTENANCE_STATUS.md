# Automated maintenance status

Observed: 2026-10-27T15:47:18+00:00. Updated by repository events and the scheduled status workflow.

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
| ci\.yml | main | queued | [Run 40534190873](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190873) |
| database-cache\.yml | main | queued | [Run 40534190892](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190892) |
| public-updates\.yml | v4\.46\.40 | failure | [Run 40528686080](https://github.com/Perseusxrltd/mnemion/actions/runs/40528686080) |
| release\.yml | release/4\.46\.40 | success | [Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119) |
| release\.yml | release/4\.46\.41 | failure | [Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699) |
| verify-artifacts\.yml | main | skipped | [Run 40532935630](https://github.com/Perseusxrltd/mnemion/actions/runs/40532935630) |
| website-release\.yml | main | success | [Run 40534190911](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190911) |
| website-release\.yml | v4\.46\.40 | success | [Run 40528680423](https://github.com/Perseusxrltd/mnemion/actions/runs/40528680423) |

## Active jobs

[Run 40534190873](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190873): 5/12 jobs completed; 5 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- supervision \(macos-26\): queued.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40534190892](https://github.com/Perseusxrltd/mnemion/actions/runs/40534190892): 2/7 jobs completed; 2 succeeded.

- database / Database / macos / x64: in\_progress — Compile pinned PostgreSQL, vector extension and static libraries.
- database / Database / linux / x64: in\_progress — Compile pinned PostgreSQL, vector extension and static libraries.
- database / Database / linux / arm64: in\_progress — Compile pinned PostgreSQL, vector extension and static libraries.
- database / Database / windows / x64: in\_progress — Compile pinned PostgreSQL, vector extension and static libraries.
- database / Database / macos / arm64: queued.


## Unsuccessful jobs

- [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882): supervision \(macos-15\) (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40528686080](https://github.com/Perseusxrltd/mnemion/actions/runs/40528686080): macos / arm64 public upgrade (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699): native / native\_database / Database / macos / arm64 (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
