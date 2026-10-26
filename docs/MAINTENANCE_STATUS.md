# Automated maintenance status

Observed: 2026-10-26T19:30:06+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.22](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.22). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40385484447](https://github.com/Perseusxrltd/mnemion/actions/runs/40385484447) |
| public-updates\.yml | v4\.46\.22 | success | [Run 40366545289](https://github.com/Perseusxrltd/mnemion/actions/runs/40366545289) |
| release\.yml | release/4\.46\.22 | success | [Run 40351425614](https://github.com/Perseusxrltd/mnemion/actions/runs/40351425614) |
| release\.yml | release/4\.46\.24 | failure | [Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179) |
| release\.yml | release/4\.46\.25 | failure | [Run 40376743057](https://github.com/Perseusxrltd/mnemion/actions/runs/40376743057) |
| release\.yml | release/4\.46\.26 | queued | [Run 40384317169](https://github.com/Perseusxrltd/mnemion/actions/runs/40384317169) |
| verify-artifacts\.yml | main | skipped | [Run 40387116328](https://github.com/Perseusxrltd/mnemion/actions/runs/40387116328) |
| website-release\.yml | main | success | [Run 40385484524](https://github.com/Perseusxrltd/mnemion/actions/runs/40385484524) |
| website-release\.yml | v4\.46\.22 | success | [Run 40366540445](https://github.com/Perseusxrltd/mnemion/actions/runs/40366540445) |

## Active jobs

[Run 40385484447](https://github.com/Perseusxrltd/mnemion/actions/runs/40385484447): 8/12 jobs completed; 8 succeeded.

- supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40384317169](https://github.com/Perseusxrltd/mnemion/actions/runs/40384317169): 7/13 jobs completed; 6 succeeded.

- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- native / native\_database / Database / linux / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Database / windows / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Database / macos / arm64: queued.
- native / native\_database / Database / linux / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Database / macos / x64: in\_progress — Set up job.


## Unsuccessful jobs

- [Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179): native / ubuntu-22\.04 / x64 (failure). Steps: Package the native desktop with one bounded upstream-download retry.
- [Run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179): native / ubuntu-22\.04-arm / arm64 (failure). Steps: Package the native desktop with one bounded upstream-download retry.
- [Run 40376743057](https://github.com/Perseusxrltd/mnemion/actions/runs/40376743057): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
