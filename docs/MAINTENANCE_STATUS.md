# Automated maintenance status

Observed: 2026-10-20T08:18:55+00:00. Updated by repository events and the scheduled status workflow.

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
| release\.yml | release/4\.34\.0 | in\_progress | [Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080) |
| release\.yml | release/4\.35\.0 | pending | [Run 39392435604](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604) |
| verify-artifacts\.yml | main | success | [Run 39387307827](https://github.com/Perseusxrltd/mnemion/actions/runs/39387307827) |
| website-release\.yml | v4\.33\.0 | success | [Run 39387465064](https://github.com/Perseusxrltd/mnemion/actions/runs/39387465064) |

## Active jobs

[Run 39392286802](https://github.com/Perseusxrltd/mnemion/actions/runs/39392286802): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Post Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.13\): in\_progress — Run python -m pip install uv==0\.12\.24.
- container \(ubuntu-22\.04\): in\_progress — Verify the non-root image includes Studio, guides and notices offline.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.

[Run 39388255080](https://github.com/Perseusxrltd/mnemion/actions/runs/39388255080): 30/31 jobs completed; 30 succeeded.

- native / windows-11-arm / arm64: in\_progress — Native Windows installation, authenticated upgrade and relaunch.

