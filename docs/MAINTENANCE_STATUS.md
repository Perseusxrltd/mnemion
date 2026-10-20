# Automated maintenance status

Observed: 2026-10-20T05:54:48+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.31.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.31.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39377250572](https://github.com/Perseusxrltd/mnemion/actions/runs/39377250572) |
| public-updates\.yml | v4\.31\.0 | success | [Run 39374937778](https://github.com/Perseusxrltd/mnemion/actions/runs/39374937778) |
| release\.yml | release/4\.31\.0-r4 | success | [Run 39371280650](https://github.com/Perseusxrltd/mnemion/actions/runs/39371280650) |
| release\.yml | release/4\.32\.0 | cancelled | [Run 39373420728](https://github.com/Perseusxrltd/mnemion/actions/runs/39373420728) |
| release\.yml | release/4\.32\.0-r2 | queued | [Run 39377381706](https://github.com/Perseusxrltd/mnemion/actions/runs/39377381706) |
| verify-artifacts\.yml | main | skipped | [Run 39377325233](https://github.com/Perseusxrltd/mnemion/actions/runs/39377325233) |
| website-release\.yml | v4\.31\.0 | success | [Run 39374935509](https://github.com/Perseusxrltd/mnemion/actions/runs/39374935509) |

## Active jobs

[Run 39377250572](https://github.com/Perseusxrltd/mnemion/actions/runs/39377250572): 7/12 jobs completed; 7 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39377381706](https://github.com/Perseusxrltd/mnemion/actions/runs/39377381706): 3/18 jobs completed; 3 succeeded.

- checks / lint: in\_progress — Post Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- checks / studio: in\_progress — Run python deploy/bundle\_studio\.py.
- native / Encrypted files / Windows / arm64: in\_progress.
- native / Encrypted files / Windows / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Private state / Windows / x64: in\_progress.
- native / native\_database / Private state / Windows / arm64: in\_progress.
- checks / service \(3\.12\): queued.
- checks / container \(ubuntu-22\.04\): queued.
- checks / legacy: queued.
- checks / dependency-audit: queued.
- checks / container \(ubuntu-22\.04-arm\): queued.
- checks / service \(3\.13\): queued.
- checks / supervision \(macos-15\): queued.
- checks / service \(3\.14\): queued.
- checks / supervision \(macos-15-intel\): queued.

