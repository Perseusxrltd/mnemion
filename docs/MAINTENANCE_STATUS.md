# Automated maintenance status

Observed: 2026-10-21T16:11:15+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.44.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.44.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | pending | [Run 39632347413](https://github.com/Perseusxrltd/mnemion/actions/runs/39632347413) |
| database-cache\.yml | main | success | [Run 39576347122](https://github.com/Perseusxrltd/mnemion/actions/runs/39576347122) |
| desktop\.yml | main | in\_progress | [Run 39628117517](https://github.com/Perseusxrltd/mnemion/actions/runs/39628117517) |
| release\.yml | release/4\.44\.1 | queued | [Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686) |
| website-release\.yml | main | success | [Run 39632347414](https://github.com/Perseusxrltd/mnemion/actions/runs/39632347414) |

## Active jobs

[Run 39628117517](https://github.com/Perseusxrltd/mnemion/actions/runs/39628117517): 7/8 jobs completed; 4 succeeded.

- macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.

[Run 39631942686](https://github.com/Perseusxrltd/mnemion/actions/runs/39631942686): 17/25 jobs completed; 16 succeeded.

- checks / supervision \(macos-15\): queued.
- checks / supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / native\_database / Database / macos / x64: queued.
- native / native\_database / Database / macos / arm64: queued.
- native / Service engine / Windows x64: in\_progress — Run actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38.

