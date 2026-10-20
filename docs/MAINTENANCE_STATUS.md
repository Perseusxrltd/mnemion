# Automated maintenance status

Observed: 2026-10-20T13:03:20+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.37.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.37.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | success | [Run 39424001891](https://github.com/Perseusxrltd/mnemion/actions/runs/39424001891) |
| public-updates\.yml | v4\.37\.0 | success | [Run 39403004762](https://github.com/Perseusxrltd/mnemion/actions/runs/39403004762) |
| release\.yml | release/4\.37\.0 | success | [Run 39397479332](https://github.com/Perseusxrltd/mnemion/actions/runs/39397479332) |
| release\.yml | release/4\.38\.0 | cancelled | [Run 39416800968](https://github.com/Perseusxrltd/mnemion/actions/runs/39416800968) |
| release\.yml | release/4\.39\.0 | success | [Run 39420061069](https://github.com/Perseusxrltd/mnemion/actions/runs/39420061069) |
| release\.yml | release/4\.40\.0 | in\_progress | [Run 39424241142](https://github.com/Perseusxrltd/mnemion/actions/runs/39424241142) |
| verify-artifacts\.yml | main | in\_progress | [Run 39426976671](https://github.com/Perseusxrltd/mnemion/actions/runs/39426976671) |
| website-release\.yml | main | success | [Run 39419893401](https://github.com/Perseusxrltd/mnemion/actions/runs/39419893401) |
| website-release\.yml | v4\.37\.0 | success | [Run 39403000169](https://github.com/Perseusxrltd/mnemion/actions/runs/39403000169) |

## Active jobs

[Run 39424241142](https://github.com/Perseusxrltd/mnemion/actions/runs/39424241142): 15/23 jobs completed; 15 succeeded.

- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- native / native\_database / Database / macos / x64: in\_progress — Relocate, initialize, verify TLS and RLS, restore backup and recover a crash.
- native / native\_database / Database / windows / x64: in\_progress — Relocate, initialize, verify TLS and RLS, restore backup and recover a crash.

[Run 39426976671](https://github.com/Perseusxrltd/mnemion/actions/runs/39426976671): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.

