# Automated maintenance status

Observed: 2026-10-20T13:52:31+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.40.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.40.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T13:39:27Z |
| [#46](https://github.com/Perseusxrltd/mnemion/issues/46) | Deployment access: Codex/Astra cannot see the existing office task and memory spaces | 2026-10-20T13:38:41Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39424001891](https://github.com/Perseusxrltd/mnemion/actions/runs/39424001891) |
| public-updates\.yml | v4\.40\.0 | queued | [Run 39434085500](https://github.com/Perseusxrltd/mnemion/actions/runs/39434085500) |
| release\.yml | release/4\.40\.0 | success | [Run 39424241142](https://github.com/Perseusxrltd/mnemion/actions/runs/39424241142) |
| release\.yml | release/4\.41\.0 | in\_progress | [Run 39428746847](https://github.com/Perseusxrltd/mnemion/actions/runs/39428746847) |
| verify-artifacts\.yml | main | success | [Run 39433889111](https://github.com/Perseusxrltd/mnemion/actions/runs/39433889111) |
| website-release\.yml | v4\.40\.0 | success | [Run 39434081456](https://github.com/Perseusxrltd/mnemion/actions/runs/39434081456) |

## Active jobs

[Run 39434085500](https://github.com/Perseusxrltd/mnemion/actions/runs/39434085500): 1/7 jobs completed; 1 succeeded.

- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: queued.

[Run 39428746847](https://github.com/Perseusxrltd/mnemion/actions/runs/39428746847): 17/24 jobs completed; 17 succeeded.

- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- checks / supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / native\_database / Database / Windows ARM host / x64 engine: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.

