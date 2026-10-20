# Automated maintenance status

Observed: 2026-10-20T08:26:45+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.33.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.33.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39392286802](https://github.com/Perseusxrltd/mnemion/actions/runs/39392286802) |
| public-updates\.yml | v4\.33\.0 | success | [Run 39387468667](https://github.com/Perseusxrltd/mnemion/actions/runs/39387468667) |
| release\.yml | release/4\.33\.0 | success | [Run 39382743155](https://github.com/Perseusxrltd/mnemion/actions/runs/39382743155) |
| release\.yml | release/4\.34\.0 | success | [Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080) |
| release\.yml | release/4\.35\.0 | queued | [Run 39392435604](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604) |
| verify-artifacts\.yml | main | in\_progress | [Run 39393375424](https://github.com/Perseusxrltd/mnemion/actions/runs/39393375424) |
| website-release\.yml | v4\.33\.0 | success | [Run 39387465064](https://github.com/Perseusxrltd/mnemion/actions/runs/39387465064) |

## Active jobs

[Run 39392286802](https://github.com/Perseusxrltd/mnemion/actions/runs/39392286802): 8/12 jobs completed; 8 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39392435604](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604): 4/18 jobs completed; 4 succeeded.

- checks / studio: in\_progress — Run python deploy/bundle\_studio\.py.
- native / Encrypted files / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / Encrypted files / Windows / x64: in\_progress — Run python -m pip install pytest cryptography==50\.0\.2.
- native / native\_database / Private state / Windows / x64: in\_progress — Install small private-state test dependencies.
- native / native\_database / Private state / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- checks / container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- checks / container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- checks / dependency-audit: in\_progress — Run uv sync --locked --no-dev --extra supervision.
- checks / service \(3\.14\): in\_progress — Initialize containers.
- checks / legacy: in\_progress — Run uv sync --locked --extra legacy --group dev.
- checks / service \(3\.12\): in\_progress — Initialize containers.
- checks / supervision \(macos-15\): queued.
- checks / supervision \(macos-15-intel\): in\_progress.
- checks / service \(3\.13\): in\_progress — Initialize containers.

[Run 39393375424](https://github.com/Perseusxrltd/mnemion/actions/runs/39393375424): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.

