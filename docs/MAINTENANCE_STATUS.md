# Automated maintenance status

Observed: 2026-10-20T05:25:39+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.30.2](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.30.2). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39374402147](https://github.com/Perseusxrltd/mnemion/actions/runs/39374402147) |
| public-updates\.yml | v4\.30\.2 | success | [Run 39364174502](https://github.com/Perseusxrltd/mnemion/actions/runs/39364174502) |
| release\.yml | release/4\.30\.2 | success | [Run 39360472861](https://github.com/Perseusxrltd/mnemion/actions/runs/39360472861) |
| release\.yml | release/4\.31\.0 | cancelled | [Run 39367799163](https://github.com/Perseusxrltd/mnemion/actions/runs/39367799163) |
| release\.yml | release/4\.31\.0-r2 | cancelled | [Run 39368210556](https://github.com/Perseusxrltd/mnemion/actions/runs/39368210556) |
| release\.yml | release/4\.31\.0-r3 | cancelled | [Run 39369300320](https://github.com/Perseusxrltd/mnemion/actions/runs/39369300320) |
| release\.yml | release/4\.31\.0-r4 | success | [Run 39371280650](https://github.com/Perseusxrltd/mnemion/actions/runs/39371280650) |
| release\.yml | release/4\.32\.0 | in\_progress | [Run 39373420728](https://github.com/Perseusxrltd/mnemion/actions/runs/39373420728) |
| verify-artifacts\.yml | main | in\_progress | [Run 39374776534](https://github.com/Perseusxrltd/mnemion/actions/runs/39374776534) |
| website-release\.yml | main | success | [Run 39373804734](https://github.com/Perseusxrltd/mnemion/actions/runs/39373804734) |
| website-release\.yml | v4\.30\.2 | success | [Run 39364171858](https://github.com/Perseusxrltd/mnemion/actions/runs/39364171858) |

## Active jobs

[Run 39374402147](https://github.com/Perseusxrltd/mnemion/actions/runs/39374402147): 8/12 jobs completed; 8 succeeded.

- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 39373420728](https://github.com/Perseusxrltd/mnemion/actions/runs/39373420728): 5/18 jobs completed; 5 succeeded.

- checks / studio: in\_progress — Run npm --prefix studio/electron ci && npm --prefix studio/electron test.
- native / Encrypted files / Windows / x64: in\_progress — Verify native encrypted files and desktop control before packaging.
- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- native / native\_database / Private state / Windows / arm64: in\_progress — Install small private-state test dependencies.
- native / native\_database / Private state / Windows / x64: in\_progress — Check ownership, inherited privacy and restricted-token access.
- checks / container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- checks / service \(3\.13\): in\_progress — Initialize containers.
- checks / service \(3\.12\): in\_progress — Initialize containers.
- checks / container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- checks / legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- checks / service \(3\.14\): in\_progress — Initialize containers.
- checks / supervision \(macos-15\): in\_progress — Install the native service without building on a managed host.
- checks / supervision \(macos-15-intel\): in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.

[Run 39374776534](https://github.com/Perseusxrltd/mnemion/actions/runs/39374776534): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.

