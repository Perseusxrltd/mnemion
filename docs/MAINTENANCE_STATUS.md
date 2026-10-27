# Automated maintenance status

Observed: 2026-10-27T12:37:12+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.38](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.38). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40505069719](https://github.com/Perseusxrltd/mnemion/actions/runs/40505069719) |
| public-updates\.yml | v4\.46\.38 | queued | [Run 40505169918](https://github.com/Perseusxrltd/mnemion/actions/runs/40505169918) |
| release\.yml | release/4\.46\.38 | success | [Run 40496801738](https://github.com/Perseusxrltd/mnemion/actions/runs/40496801738) |
| release\.yml | release/4\.46\.39 | in\_progress | [Run 40504681891](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891) |
| verify-artifacts\.yml | main | in\_progress | [Run 40504337244](https://github.com/Perseusxrltd/mnemion/actions/runs/40504337244) |
| website-release\.yml | main | success | [Run 40492261245](https://github.com/Perseusxrltd/mnemion/actions/runs/40492261245) |
| website-release\.yml | v4\.46\.38 | in\_progress | [Run 40505165922](https://github.com/Perseusxrltd/mnemion/actions/runs/40505165922) |

## Active jobs

[Run 40505069719](https://github.com/Perseusxrltd/mnemion/actions/runs/40505069719): 4/12 jobs completed; 4 succeeded.

- studio: in\_progress — Run npm --prefix studio/frontend run test:map.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40505169918](https://github.com/Perseusxrltd/mnemion/actions/runs/40505169918): 0/1 jobs completed; 0 succeeded.

- select: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.

[Run 40504681891](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891): 14/15 jobs completed; 13 succeeded.

- native / Service engine / Windows x64: in\_progress — Run uv run --no-sync python -m deploy\.build\_native\_engine --work build-tmp/windows-engine-build --output build-tmp/windows-engine.

[Run 40505165922](https://github.com/Perseusxrltd/mnemion/actions/runs/40505165922): 0/1 jobs completed; 0 succeeded.

- synchronize: in\_progress — Validate and publish the Git-owned product documentation.

