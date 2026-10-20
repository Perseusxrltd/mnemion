# Automated maintenance status

Observed: 2026-10-20T12:09:52+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.37.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.37.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T11:54:56Z |
| [#46](https://github.com/Perseusxrltd/mnemion/issues/46) | Deployment access: Codex/Astra cannot see the existing office task and memory spaces | 2026-10-20T12:05:17Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39419696237](https://github.com/Perseusxrltd/mnemion/actions/runs/39419696237) |
| public-updates\.yml | v4\.37\.0 | success | [Run 39403004762](https://github.com/Perseusxrltd/mnemion/actions/runs/39403004762) |
| release\.yml | release/4\.37\.0 | success | [Run 39397479332](https://github.com/Perseusxrltd/mnemion/actions/runs/39397479332) |
| release\.yml | release/4\.38\.0 | cancelled | [Run 39416800968](https://github.com/Perseusxrltd/mnemion/actions/runs/39416800968) |
| release\.yml | release/4\.39\.0 | in\_progress | [Run 39420061069](https://github.com/Perseusxrltd/mnemion/actions/runs/39420061069) |
| verify-artifacts\.yml | main | skipped | [Run 39420041429](https://github.com/Perseusxrltd/mnemion/actions/runs/39420041429) |
| website-release\.yml | main | success | [Run 39419893401](https://github.com/Perseusxrltd/mnemion/actions/runs/39419893401) |
| website-release\.yml | v4\.37\.0 | success | [Run 39403000169](https://github.com/Perseusxrltd/mnemion/actions/runs/39403000169) |

## Active jobs

[Run 39419696237](https://github.com/Perseusxrltd/mnemion/actions/runs/39419696237): 7/12 jobs completed; 7 succeeded.

- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39420061069](https://github.com/Perseusxrltd/mnemion/actions/runs/39420061069): 7/18 jobs completed; 7 succeeded.

- checks / studio: in\_progress — Run npm --prefix studio/electron ci && npm --prefix studio/electron test.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- checks / service \(3\.13\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- checks / container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- checks / supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- native / native\_database / Private state / Windows / arm64: in\_progress — Post Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.

