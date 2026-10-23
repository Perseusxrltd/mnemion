# Automated maintenance status

Observed: 2026-10-23T11:36:51+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.1](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.1). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 39947061896](https://github.com/Perseusxrltd/mnemion/actions/runs/39947061896) |
| database-cache\.yml | main | success | [Run 39931143679](https://github.com/Perseusxrltd/mnemion/actions/runs/39931143679) |
| public-updates\.yml | v4\.46\.1 | success | [Run 39925663475](https://github.com/Perseusxrltd/mnemion/actions/runs/39925663475) |
| release\.yml | release/4\.46\.1-r2 | success | [Run 39916372505](https://github.com/Perseusxrltd/mnemion/actions/runs/39916372505) |
| release\.yml | release/4\.46\.2 | in\_progress | [Run 39945380878](https://github.com/Perseusxrltd/mnemion/actions/runs/39945380878) |
| verify-artifacts\.yml | main | success | [Run 39925023152](https://github.com/Perseusxrltd/mnemion/actions/runs/39925023152) |
| website-release\.yml | main | success | [Run 39947061851](https://github.com/Perseusxrltd/mnemion/actions/runs/39947061851) |
| website-release\.yml | v4\.46\.1 | success | [Run 39925659880](https://github.com/Perseusxrltd/mnemion/actions/runs/39925659880) |

## Active jobs

[Run 39947061896](https://github.com/Perseusxrltd/mnemion/actions/runs/39947061896): 3/12 jobs completed; 3 succeeded.

- studio: in\_progress — Run python deploy/bundle\_studio\.py.
- service \(3\.14\): in\_progress — Run python -m pip install uv==0\.12\.24.
- service \(3\.13\): in\_progress — Initialize containers.
- service \(3\.12\): in\_progress — Run python -m pip install uv==0\.12\.24.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- supervision \(macos-15-intel\): in\_progress — Run python -m pip install uv==0\.12\.24.

[Run 39945380878](https://github.com/Perseusxrltd/mnemion/actions/runs/39945380878): 23/32 jobs completed; 22 succeeded.

- checks / service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- checks / service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- native / macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / windows-2022 / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- native / macos-15-intel / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.

