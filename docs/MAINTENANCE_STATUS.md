# Automated maintenance status

Observed: 2026-10-27T14:45:45+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.39](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.39). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | codex/telemetry-sql-reads-20261027 | queued | [Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882) |
| ci\.yml | main | queued | [Run 40524093039](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039) |
| public-updates\.yml | v4\.46\.39 | success | [Run 40521216857](https://github.com/Perseusxrltd/mnemion/actions/runs/40521216857) |
| release\.yml | release/4\.46\.39 | success | [Run 40504681891](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891) |
| release\.yml | release/4\.46\.40 | in\_progress | [Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119) |
| release\.yml | release/4\.46\.41 | pending | [Run 40523707699](https://github.com/Perseusxrltd/mnemion/actions/runs/40523707699) |
| verify-artifacts\.yml | main | success | [Run 40512666290](https://github.com/Perseusxrltd/mnemion/actions/runs/40512666290) |
| website-release\.yml | main | success | [Run 40524092744](https://github.com/Perseusxrltd/mnemion/actions/runs/40524092744) |
| website-release\.yml | v4\.46\.39 | success | [Run 40521210268](https://github.com/Perseusxrltd/mnemion/actions/runs/40521210268) |

## Active jobs

[Run 40523497882](https://github.com/Perseusxrltd/mnemion/actions/runs/40523497882): 7/12 jobs completed; 7 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15\): queued.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.

[Run 40524093039](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix packages/client test.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04\): queued.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): queued.

[Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119): 20/21 jobs completed; 19 succeeded.

- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

