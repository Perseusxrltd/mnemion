# Automated maintenance status

Observed: 2026-10-20T13:04:32+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.39.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.39.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T11:54:56Z |
| [#46](https://github.com/Perseusxrltd/mnemion/issues/46) | Deployment access: Codex/Astra cannot see the existing office task and memory spaces | 2026-10-20T13:02:49Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39419696237](https://github.com/Perseusxrltd/mnemion/actions/runs/39419696237) |
| public-updates\.yml | v4\.39\.0 | in\_progress | [Run 39427237766](https://github.com/Perseusxrltd/mnemion/actions/runs/39427237766) |
| release\.yml | release/4\.39\.0 | success | [Run 39420061069](https://github.com/Perseusxrltd/mnemion/actions/runs/39420061069) |
| release\.yml | release/4\.40\.0 | in\_progress | [Run 39424241142](https://github.com/Perseusxrltd/mnemion/actions/runs/39424241142) |
| verify-artifacts\.yml | main | success | [Run 39426976671](https://github.com/Perseusxrltd/mnemion/actions/runs/39426976671) |
| website-release\.yml | v4\.39\.0 | success | [Run 39427234119](https://github.com/Perseusxrltd/mnemion/actions/runs/39427234119) |

## Active jobs

[Run 39427237766](https://github.com/Perseusxrltd/mnemion/actions/runs/39427237766): 1/7 jobs completed; 1 succeeded.

- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 39424241142](https://github.com/Perseusxrltd/mnemion/actions/runs/39424241142): 17/24 jobs completed; 17 succeeded.

- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- native / native\_database / Database / Windows ARM host / x64 engine: in\_progress — Verify the actual x64 engine under Windows ARM emulation.

