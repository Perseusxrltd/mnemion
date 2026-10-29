# Automated maintenance status

Observed: 2026-10-29T03:59:27+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.48](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.48). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

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
| ci\.yml | main | in\_progress | [Run 40812214715](https://github.com/Perseusxrltd/mnemion/actions/runs/40812214715) |
| public-updates\.yml | v4\.46\.48 | success | [Run 40814044656](https://github.com/Perseusxrltd/mnemion/actions/runs/40814044656) |
| release\.yml | release/4\.46\.48 | success | [Run 40806507811](https://github.com/Perseusxrltd/mnemion/actions/runs/40806507811) |
| release\.yml | release/4\.46\.49 | in\_progress | [Run 40812422400](https://github.com/Perseusxrltd/mnemion/actions/runs/40812422400) |
| verify-artifacts\.yml | main | success | [Run 40813597891](https://github.com/Perseusxrltd/mnemion/actions/runs/40813597891) |
| website-release\.yml | main | success | [Run 40802930121](https://github.com/Perseusxrltd/mnemion/actions/runs/40802930121) |
| website-release\.yml | v4\.46\.48 | success | [Run 40814041922](https://github.com/Perseusxrltd/mnemion/actions/runs/40814041922) |

## Active jobs

[Run 40812214715](https://github.com/Perseusxrltd/mnemion/actions/runs/40812214715): 11/12 jobs completed; 11 succeeded.

- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40812422400](https://github.com/Perseusxrltd/mnemion/actions/runs/40812422400): 15/21 jobs completed; 14 succeeded.

- native / ubuntu-22\.04 / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / macos-26 / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / macos-15-intel / x64: in\_progress — Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
- native / windows-11-arm / arm64: in\_progress — Run npm --prefix packages/client ci.
- native / windows-2022 / x64: in\_progress — Run npm --prefix studio/electron test.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.

