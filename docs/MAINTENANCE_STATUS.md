# Automated maintenance status

Observed: 2026-10-26T06:16:52+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.13](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.13). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40278695164](https://github.com/Perseusxrltd/mnemion/actions/runs/40278695164) |
| public-updates\.yml | v4\.46\.13 | success | [Run 40268195296](https://github.com/Perseusxrltd/mnemion/actions/runs/40268195296) |
| release\.yml | release/4\.46\.13 | success | [Run 40262676121](https://github.com/Perseusxrltd/mnemion/actions/runs/40262676121) |
| verify-artifacts\.yml | main | success | [Run 40267817685](https://github.com/Perseusxrltd/mnemion/actions/runs/40267817685) |
| website-release\.yml | main | success | [Run 40278695165](https://github.com/Perseusxrltd/mnemion/actions/runs/40278695165) |
| website-release\.yml | v4\.46\.13 | success | [Run 40268192045](https://github.com/Perseusxrltd/mnemion/actions/runs/40268192045) |

## Active jobs

[Run 40278695164](https://github.com/Perseusxrltd/mnemion/actions/runs/40278695164): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.12\): in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.

