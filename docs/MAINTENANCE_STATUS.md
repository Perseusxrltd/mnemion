# Automated maintenance status

Observed: 2026-10-28T17:57:35+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.44](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.44). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#47](https://github.com/Perseusxrltd/mnemion/issues/47) | Field report \(4\.46\.40\): multi-agent usage audit — slow/hanging search, suspended connector scope, noisy activity log, unusable vault over MCP, and features left unused | 2026-10-28T17:01:24Z |
| [#48](https://github.com/Perseusxrltd/mnemion/issues/48) | Mnemion as the single system: full replacement of LEDGER/DISPATCH/files, plus vault compatibility | 2026-10-28T09:04:09Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 40740459623](https://github.com/Perseusxrltd/mnemion/actions/runs/40740459623) |
| public-updates\.yml | v4\.46\.44 | failure | [Run 40702705371](https://github.com/Perseusxrltd/mnemion/actions/runs/40702705371) |
| release\.yml | release/4\.46\.44 | success | [Run 40690852078](https://github.com/Perseusxrltd/mnemion/actions/runs/40690852078) |
| release\.yml | release/4\.46\.45 | failure | [Run 40695913724](https://github.com/Perseusxrltd/mnemion/actions/runs/40695913724) |
| verify-artifacts\.yml | main | skipped | [Run 40713875652](https://github.com/Perseusxrltd/mnemion/actions/runs/40713875652) |
| website-release\.yml | main | success | [Run 40740459240](https://github.com/Perseusxrltd/mnemion/actions/runs/40740459240) |
| website-release\.yml | v4\.46\.44 | success | [Run 40702700363](https://github.com/Perseusxrltd/mnemion/actions/runs/40702700363) |

## Active jobs

[Run 40740459623](https://github.com/Perseusxrltd/mnemion/actions/runs/40740459623): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.12\): in\_progress — Run actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Matching PostgreSQL recovery tools.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-26\): queued.


## Unsuccessful jobs

- [Run 40702705371](https://github.com/Perseusxrltd/mnemion/actions/runs/40702705371): macos / arm64 public upgrade (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
- [Run 40695913724](https://github.com/Perseusxrltd/mnemion/actions/runs/40695913724): native / macos-26 / arm64 (cancelled). No unsuccessful step was reported. No runner was assigned and no steps were reported.
