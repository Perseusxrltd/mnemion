# Automated maintenance status

Observed: 2026-10-27T07:05:53+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.36](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.36). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40464963472](https://github.com/Perseusxrltd/mnemion/actions/runs/40464963472) |
| public-updates\.yml | v4\.46\.36 | success | [Run 40456607379](https://github.com/Perseusxrltd/mnemion/actions/runs/40456607379) |
| release\.yml | release/4\.46\.36 | success | [Run 40451445143](https://github.com/Perseusxrltd/mnemion/actions/runs/40451445143) |
| release\.yml | release/4\.46\.37 | in\_progress | [Run 40462412553](https://github.com/Perseusxrltd/mnemion/actions/runs/40462412553) |
| verify-artifacts\.yml | main | success | [Run 40456226983](https://github.com/Perseusxrltd/mnemion/actions/runs/40456226983) |
| website-release\.yml | main | success | [Run 40464963516](https://github.com/Perseusxrltd/mnemion/actions/runs/40464963516) |
| website-release\.yml | v4\.46\.36 | success | [Run 40456602936](https://github.com/Perseusxrltd/mnemion/actions/runs/40456602936) |

## Active jobs

[Run 40464963472](https://github.com/Perseusxrltd/mnemion/actions/runs/40464963472): 4/12 jobs completed; 4 succeeded.

- studio: in\_progress — Run npm --prefix studio/electron test.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.

[Run 40462412553](https://github.com/Perseusxrltd/mnemion/actions/runs/40462412553): 16/21 jobs completed; 15 succeeded.

- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15 / arm64: in\_progress — Sign and verify the free macOS update archive.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

