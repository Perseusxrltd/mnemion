# Automated maintenance status

Observed: 2026-10-26T23:10:38+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.28](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.28). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40416515726](https://github.com/Perseusxrltd/mnemion/actions/runs/40416515726) |
| public-updates\.yml | v4\.46\.28 | success | [Run 40411258731](https://github.com/Perseusxrltd/mnemion/actions/runs/40411258731) |
| release\.yml | release/4\.46\.28 | success | [Run 40399013490](https://github.com/Perseusxrltd/mnemion/actions/runs/40399013490) |
| release\.yml | release/4\.46\.29 | success | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| release\.yml | release/4\.46\.30 | queued | [Run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100) |
| release\.yml | release/4\.46\.31 | pending | [Run 40417437026](https://github.com/Perseusxrltd/mnemion/actions/runs/40417437026) |
| verify-artifacts\.yml | main | failure | [Run 40417189624](https://github.com/Perseusxrltd/mnemion/actions/runs/40417189624) |
| website-release\.yml | main | success | [Run 40416515248](https://github.com/Perseusxrltd/mnemion/actions/runs/40416515248) |
| website-release\.yml | v4\.46\.28 | success | [Run 40411254189](https://github.com/Perseusxrltd/mnemion/actions/runs/40411254189) |

## Active jobs

[Run 40416515726](https://github.com/Perseusxrltd/mnemion/actions/runs/40416515726): 8/12 jobs completed; 8 succeeded.

- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100): 15/21 jobs completed; 14 succeeded.

- native / windows-11-arm / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / macos-15 / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / ubuntu-22\.04 / x64: in\_progress — Run actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38.
- native / windows-2022 / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Set up job.
- native / macos-15-intel / x64: in\_progress — Set up job.


## Unsuccessful jobs

- [Run 40417189624](https://github.com/Perseusxrltd/mnemion/actions/runs/40417189624): verify (failure). Steps: Scan the exact downloaded distributions before publication.
