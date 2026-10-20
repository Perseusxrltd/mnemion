# Automated maintenance status

Observed: 2026-10-20T08:28:07+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.34.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.34.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39392286802](https://github.com/Perseusxrltd/mnemion/actions/runs/39392286802) |
| public-updates\.yml | v4\.34\.0 | in\_progress | [Run 39393538181](https://github.com/Perseusxrltd/mnemion/actions/runs/39393538181) |
| release\.yml | release/4\.34\.0 | success | [Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080) |
| release\.yml | release/4\.35\.0 | in\_progress | [Run 39392435604](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604) |
| verify-artifacts\.yml | main | success | [Run 39393375424](https://github.com/Perseusxrltd/mnemion/actions/runs/39393375424) |
| website-release\.yml | v4\.34\.0 | success | [Run 39393535317](https://github.com/Perseusxrltd/mnemion/actions/runs/39393535317) |

## Active jobs

[Run 39392286802](https://github.com/Perseusxrltd/mnemion/actions/runs/39392286802): 8/12 jobs completed; 8 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39393538181](https://github.com/Perseusxrltd/mnemion/actions/runs/39393538181): 1/7 jobs completed; 1 succeeded.

- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Run python -m pip install psutil==7\.2\.2.
- linux / x64 public upgrade: in\_progress — Linux desktop libraries.
- macos / arm64 public upgrade: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.

[Run 39392435604](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604): 17/24 jobs completed; 17 succeeded.

- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / native\_database / Database / Windows ARM host / x64 engine: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.

