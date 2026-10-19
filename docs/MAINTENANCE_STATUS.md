# Automated maintenance status

Observed: 2026-10-19T17:50:52+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.20.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.20.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds are checked for failed jobs at each observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (9)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#3](https://github.com/Perseusxrltd/mnemion/issues/3) | No built-in remote access option; operators must bring their own reverse proxy / tunnel | 2026-10-11T03:04:30Z |
| [#4](https://github.com/Perseusxrltd/mnemion/issues/4) | No OAuth for hosted agents; static bearer tokens only | 2026-10-10T20:55:33Z |
| [#17](https://github.com/Perseusxrltd/mnemion/issues/17) | Natural-language questions retrieve much worse than keyword queries | 2026-10-19T07:56:12Z |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |
| [#31](https://github.com/Perseusxrltd/mnemion/issues/31) | Recall has no recency signal: older 'open question' memories outrank the newer answer | 2026-10-19T16:14:52Z |
| [#32](https://github.com/Perseusxrltd/mnemion/issues/32) | Feature: encrypted secrets vault, kept apart from searchable memory | 2026-10-19T09:43:02Z |
| [#38](https://github.com/Perseusxrltd/mnemion/issues/38) | Host reset wipes a self-hosted install with no reproducible re-install path or off-host key/state recovery | 2026-10-19T12:13:43Z |
| [#39](https://github.com/Perseusxrltd/mnemion/issues/39) | Buffer memory with automatic additive write-back to Git \(native saves are never pushed upstream\) | 2026-10-19T11:44:25Z |
| [#43](https://github.com/Perseusxrltd/mnemion/issues/43) | Filesystem connector: one non-UTF-8 text file suspends the whole scope \(access\_suspended\) with no health signal | 2026-10-19T16:14:43Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | failure | [Run 39295360468](https://github.com/Perseusxrltd/mnemion/actions/runs/39295360468) |
| public-updates\.yml | v4\.20\.0 | success | [Run 39292701099](https://github.com/Perseusxrltd/mnemion/actions/runs/39292701099) |
| release\.yml | release/4\.20\.0 | success | [Run 39283268591](https://github.com/Perseusxrltd/mnemion/actions/runs/39283268591) |
| release\.yml | release/4\.21\.0 | cancelled | [Run 39287754923](https://github.com/Perseusxrltd/mnemion/actions/runs/39287754923) |
| release\.yml | release/4\.22\.0 | queued | [Run 39295434988](https://github.com/Perseusxrltd/mnemion/actions/runs/39295434988) |
| verify-artifacts\.yml | main | skipped | [Run 39295760633](https://github.com/Perseusxrltd/mnemion/actions/runs/39295760633) |
| website-release\.yml | v4\.20\.0 | success | [Run 39292701228](https://github.com/Perseusxrltd/mnemion/actions/runs/39292701228) |

## Failed jobs

- [Run 39295360468](https://github.com/Perseusxrltd/mnemion/actions/runs/39295360468): service \(3\.13\). Steps: Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- [Run 39295360468](https://github.com/Perseusxrltd/mnemion/actions/runs/39295360468): service \(3\.14\). Steps: Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- [Run 39295360468](https://github.com/Perseusxrltd/mnemion/actions/runs/39295360468): service \(3\.12\). Steps: Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- [Run 39295434988](https://github.com/Perseusxrltd/mnemion/actions/runs/39295434988): checks / service \(3\.14\). Steps: Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- [Run 39295434988](https://github.com/Perseusxrltd/mnemion/actions/runs/39295434988): checks / service \(3\.13\). Steps: Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
