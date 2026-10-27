# Automated maintenance status

Observed: 2026-10-27T12:09:06+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.37](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.37). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40501408853](https://github.com/Perseusxrltd/mnemion/actions/runs/40501408853) |
| database-cache\.yml | main | success | [Run 40483624017](https://github.com/Perseusxrltd/mnemion/actions/runs/40483624017) |
| public-updates\.yml | v4\.46\.37 | success | [Run 40474484566](https://github.com/Perseusxrltd/mnemion/actions/runs/40474484566) |
| release\.yml | release/4\.46\.37 | success | [Run 40462412553](https://github.com/Perseusxrltd/mnemion/actions/runs/40462412553) |
| release\.yml | release/4\.46\.38 | in\_progress | [Run 40496801738](https://github.com/Perseusxrltd/mnemion/actions/runs/40496801738) |
| verify-artifacts\.yml | main | failure | [Run 40468253346](https://github.com/Perseusxrltd/mnemion/actions/runs/40468253346) |
| website-release\.yml | main | success | [Run 40501408889](https://github.com/Perseusxrltd/mnemion/actions/runs/40501408889) |
| website-release\.yml | v4\.46\.37 | success | [Run 40474480217](https://github.com/Perseusxrltd/mnemion/actions/runs/40474480217) |

## Active jobs

[Run 40501408853](https://github.com/Perseusxrltd/mnemion/actions/runs/40501408853): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run npm --prefix studio/frontend run test:telemetry.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- container \(ubuntu-22\.04\): in\_progress — Verify the non-root image includes Studio, guides and notices offline.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): in\_progress — Run npm --prefix packages/client ci && npm --prefix packages/client test.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.14\): in\_progress — Check release versions before building clients and running the service matrix.

[Run 40496801738](https://github.com/Perseusxrltd/mnemion/actions/runs/40496801738): 19/21 jobs completed; 18 succeeded.

- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Packaged Mac update, restart guards and relaunch.


## Unsuccessful jobs

- [Run 40468253346](https://github.com/Perseusxrltd/mnemion/actions/runs/40468253346): verify (failure). Steps: Scan the exact downloaded distributions before publication.
