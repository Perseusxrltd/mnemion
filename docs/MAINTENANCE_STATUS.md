# Automated maintenance status

Observed: 2026-10-27T09:51:51+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.37](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.37). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40483312151](https://github.com/Perseusxrltd/mnemion/actions/runs/40483312151) |
| database-cache\.yml | main | success | [Run 40483624017](https://github.com/Perseusxrltd/mnemion/actions/runs/40483624017) |
| public-updates\.yml | v4\.46\.37 | success | [Run 40474484566](https://github.com/Perseusxrltd/mnemion/actions/runs/40474484566) |
| release\.yml | release/4\.46\.37 | success | [Run 40462412553](https://github.com/Perseusxrltd/mnemion/actions/runs/40462412553) |
| verify-artifacts\.yml | main | failure | [Run 40468253346](https://github.com/Perseusxrltd/mnemion/actions/runs/40468253346) |
| website-release\.yml | main | success | [Run 40483312113](https://github.com/Perseusxrltd/mnemion/actions/runs/40483312113) |
| website-release\.yml | v4\.46\.37 | success | [Run 40474480217](https://github.com/Perseusxrltd/mnemion/actions/runs/40474480217) |

## Active jobs

[Run 40483312151](https://github.com/Perseusxrltd/mnemion/actions/runs/40483312151): 8/12 jobs completed; 7 succeeded.

- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.


## Unsuccessful jobs

- [Run 40483312151](https://github.com/Perseusxrltd/mnemion/actions/runs/40483312151): legacy (failure). Steps: Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- [Run 40468253346](https://github.com/Perseusxrltd/mnemion/actions/runs/40468253346): verify (failure). Steps: Scan the exact downloaded distributions before publication.
