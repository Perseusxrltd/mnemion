# Automated maintenance status

Observed: 2026-10-26T21:57:50+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.27](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.27). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40408566855](https://github.com/Perseusxrltd/mnemion/actions/runs/40408566855) |
| public-updates\.yml | v4\.46\.27 | success | [Run 40403841976](https://github.com/Perseusxrltd/mnemion/actions/runs/40403841976) |
| release\.yml | release/4\.46\.27 | success | [Run 40391018946](https://github.com/Perseusxrltd/mnemion/actions/runs/40391018946) |
| release\.yml | release/4\.46\.28 | in\_progress | [Run 40399013490](https://github.com/Perseusxrltd/mnemion/actions/runs/40399013490) |
| release\.yml | release/4\.46\.29 | pending | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| verify-artifacts\.yml | main | success | [Run 40402981613](https://github.com/Perseusxrltd/mnemion/actions/runs/40402981613) |
| website-release\.yml | main | success | [Run 40408566878](https://github.com/Perseusxrltd/mnemion/actions/runs/40408566878) |
| website-release\.yml | v4\.46\.27 | success | [Run 40403837950](https://github.com/Perseusxrltd/mnemion/actions/runs/40403837950) |

## Active jobs

[Run 40408566855](https://github.com/Perseusxrltd/mnemion/actions/runs/40408566855): 4/12 jobs completed; 4 succeeded.

- studio: in\_progress — Run npm --prefix studio/frontend run test:telemetry.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.

[Run 40399013490](https://github.com/Perseusxrltd/mnemion/actions/runs/40399013490): 20/21 jobs completed; 19 succeeded.

- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

