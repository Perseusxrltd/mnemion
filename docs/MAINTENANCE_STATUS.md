# Automated maintenance status

Observed: 2026-10-22T14:08:49+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.44.2](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.44.2). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 39792490489](https://github.com/Perseusxrltd/mnemion/actions/runs/39792490489) |
| desktop\.yml | main | in\_progress | [Run 39788603173](https://github.com/Perseusxrltd/mnemion/actions/runs/39788603173) |
| public-updates\.yml | v4\.44\.2 | success | [Run 39762122867](https://github.com/Perseusxrltd/mnemion/actions/runs/39762122867) |
| release\.yml | release/4\.44\.2 | success | [Run 39753067641](https://github.com/Perseusxrltd/mnemion/actions/runs/39753067641) |
| verify-artifacts\.yml | main | success | [Run 39761844389](https://github.com/Perseusxrltd/mnemion/actions/runs/39761844389) |
| website-release\.yml | main | success | [Run 39792490365](https://github.com/Perseusxrltd/mnemion/actions/runs/39792490365) |
| website-release\.yml | v4\.44\.2 | success | [Run 39762118327](https://github.com/Perseusxrltd/mnemion/actions/runs/39762118327) |

## Active jobs

[Run 39792490489](https://github.com/Perseusxrltd/mnemion/actions/runs/39792490489): 3/12 jobs completed; 2 succeeded.

- studio: in\_progress.
- Select checks: in\_progress.
- container \(ubuntu-22\.04\): in\_progress.
- service \(3\.12\): queued.
- service \(3\.14\): queued.
- supervision \(macos-15\): queued.
- supervision \(macos-15-intel\): in\_progress.
- service \(3\.13\): queued.
- legacy: queued.

[Run 39788603173](https://github.com/Perseusxrltd/mnemion/actions/runs/39788603173): 13/18 jobs completed; 12 succeeded.

- ubuntu-22\.04 / x64: in\_progress — Installed Linux app creates, searches and reopens a real local workspace.
- macos-15 / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- macos-15-intel / x64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- windows-11-arm / arm64: in\_progress — Installed app creates, searches and reopens a real local workspace.
- ubuntu-22\.04-arm / arm64: in\_progress.


## Unsuccessful jobs

- [Run 39792490489](https://github.com/Perseusxrltd/mnemion/actions/runs/39792490489): lint (failure). Steps: Run python deploy/release\.py.
- [Run 39788603173](https://github.com/Perseusxrltd/mnemion/actions/runs/39788603173): windows-2022 / x64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
