# Automated maintenance status

Observed: 2026-10-24T01:50:28+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.5](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.5). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40051306831](https://github.com/Perseusxrltd/mnemion/actions/runs/40051306831) |
| public-updates\.yml | v4\.46\.5 | success | [Run 40022243634](https://github.com/Perseusxrltd/mnemion/actions/runs/40022243634) |
| release\.yml | release/4\.46\.5-r2 | success | [Run 40013991029](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029) |
| release\.yml | release/4\.46\.6 | success | [Run 40047223740](https://github.com/Perseusxrltd/mnemion/actions/runs/40047223740) |
| verify-artifacts\.yml | main | in\_progress | [Run 40051560833](https://github.com/Perseusxrltd/mnemion/actions/runs/40051560833) |
| website-release\.yml | main | success | [Run 40051306838](https://github.com/Perseusxrltd/mnemion/actions/runs/40051306838) |
| website-release\.yml | v4\.46\.5 | success | [Run 40022240433](https://github.com/Perseusxrltd/mnemion/actions/runs/40022240433) |

## Active jobs

[Run 40051306831](https://github.com/Perseusxrltd/mnemion/actions/runs/40051306831): 7/12 jobs completed; 7 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40051560833](https://github.com/Perseusxrltd/mnemion/actions/runs/40051560833): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.

