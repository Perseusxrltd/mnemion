# Automated maintenance status

Observed: 2026-10-20T08:31:12+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.34.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.34.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 39393856803](https://github.com/Perseusxrltd/mnemion/actions/runs/39393856803) |
| public-updates\.yml | v4\.34\.0 | in\_progress | [Run 39393538181](https://github.com/Perseusxrltd/mnemion/actions/runs/39393538181) |
| release\.yml | release/4\.34\.0 | success | [Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080) |
| release\.yml | release/4\.35\.0 | in\_progress | [Run 39392435604](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604) |
| verify-artifacts\.yml | main | success | [Run 39393375424](https://github.com/Perseusxrltd/mnemion/actions/runs/39393375424) |
| website-release\.yml | v4\.34\.0 | success | [Run 39393535317](https://github.com/Perseusxrltd/mnemion/actions/runs/39393535317) |

## Active jobs

[Run 39393856803](https://github.com/Perseusxrltd/mnemion/actions/runs/39393856803): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron ci && npm --prefix studio/electron test.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15-intel\): queued.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- container \(ubuntu-22\.04-arm\): queued.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.

[Run 39393538181](https://github.com/Perseusxrltd/mnemion/actions/runs/39393538181): 1/7 jobs completed; 1 succeeded.

- linux / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 39392435604](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604): 19/25 jobs completed; 19 succeeded.

- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15\): in\_progress — Verify both pinned local models on the actual Mac runtime.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / Service engine / Windows x64: in\_progress — Post Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.

