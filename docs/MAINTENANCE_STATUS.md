# Automated maintenance status

Observed: 2026-10-21T02:12:30+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.43.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.43.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39531567888](https://github.com/Perseusxrltd/mnemion/actions/runs/39531567888) |
| public-updates\.yml | v4\.43\.0 | success | [Run 39518522368](https://github.com/Perseusxrltd/mnemion/actions/runs/39518522368) |
| release\.yml | release/4\.43\.0 | success | [Run 39460885775](https://github.com/Perseusxrltd/mnemion/actions/runs/39460885775) |
| release\.yml | release/4\.44\.0 | in\_progress | [Run 39530357580](https://github.com/Perseusxrltd/mnemion/actions/runs/39530357580) |
| verify-artifacts\.yml | main | success | [Run 39518325759](https://github.com/Perseusxrltd/mnemion/actions/runs/39518325759) |
| website-release\.yml | main | success | [Run 39530171313](https://github.com/Perseusxrltd/mnemion/actions/runs/39530171313) |
| website-release\.yml | v4\.43\.0 | success | [Run 39518520187](https://github.com/Perseusxrltd/mnemion/actions/runs/39518520187) |

## Active jobs

[Run 39531567888](https://github.com/Perseusxrltd/mnemion/actions/runs/39531567888): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Verify wheel and source package include the matching web Studio.
- service \(3\.14\): in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- service \(3\.12\): in\_progress — Run actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38.
- service \(3\.13\): in\_progress — Run python -m pip install uv==0\.12\.24.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.

[Run 39530357580](https://github.com/Perseusxrltd/mnemion/actions/runs/39530357580): 23/32 jobs completed; 22 succeeded.

- checks / supervision \(macos-15-intel\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.

