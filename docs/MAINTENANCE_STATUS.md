# Automated maintenance status

Observed: 2026-10-20T07:47:33+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.33.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.33.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39388058383](https://github.com/Perseusxrltd/mnemion/actions/runs/39388058383) |
| public-updates\.yml | v4\.33\.0 | success | [Run 39387468667](https://github.com/Perseusxrltd/mnemion/actions/runs/39387468667) |
| release\.yml | release/4\.33\.0 | success | [Run 39382743155](https://github.com/Perseusxrltd/mnemion/actions/runs/39382743155) |
| release\.yml | release/4\.34\.0 | in\_progress | [Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080) |
| verify-artifacts\.yml | main | success | [Run 39387307827](https://github.com/Perseusxrltd/mnemion/actions/runs/39387307827) |
| website-release\.yml | v4\.33\.0 | success | [Run 39387465064](https://github.com/Perseusxrltd/mnemion/actions/runs/39387465064) |

## Active jobs

[Run 39388058383](https://github.com/Perseusxrltd/mnemion/actions/runs/39388058383): 8/12 jobs completed; 8 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.

[Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080): 20/31 jobs completed; 20 succeeded.

- checks / supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / windows-11-arm / arm64: in\_progress — Run actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38.
- native / macos-15 / arm64: in\_progress — Locked native service build dependencies.
- native / ubuntu-22\.04 / x64: in\_progress — Linux desktop libraries.
- native / windows-2022 / x64: in\_progress — Run actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38.
- native / macos-15-intel / x64: in\_progress — Run uv sync --project studio/client --locked --python "/Users/runner/hostedtoolcache/Python/3\.13\.15/x64/bin/python" --no-managed-python.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Linux desktop libraries.

