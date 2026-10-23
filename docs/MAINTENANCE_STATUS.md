# Automated maintenance status

Observed: 2026-10-23T19:49:50+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.4](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.4). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40014217829](https://github.com/Perseusxrltd/mnemion/actions/runs/40014217829) |
| public-updates\.yml | v4\.46\.4 | success | [Run 40005404536](https://github.com/Perseusxrltd/mnemion/actions/runs/40005404536) |
| release\.yml | release/4\.46\.4 | success | [Run 39997298864](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864) |
| release\.yml | release/4\.46\.5 | failure | [Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734) |
| release\.yml | release/4\.46\.5-r2 | in\_progress | [Run 40013991029](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029) |
| verify-artifacts\.yml | main | skipped | [Run 40011337514](https://github.com/Perseusxrltd/mnemion/actions/runs/40011337514) |
| website-release\.yml | main | success | [Run 40014218141](https://github.com/Perseusxrltd/mnemion/actions/runs/40014218141) |
| website-release\.yml | v4\.46\.4 | success | [Run 40005399880](https://github.com/Perseusxrltd/mnemion/actions/runs/40005399880) |

## Active jobs

[Run 40013991029](https://github.com/Perseusxrltd/mnemion/actions/runs/40013991029): 12/14 jobs completed; 11 succeeded.

- native / native\_database / Database / linux / arm64: in\_progress — Compile pinned PostgreSQL, vector extension and static libraries.
- native / Service engine / Windows x64: in\_progress — Run uv run --no-sync python -m deploy\.build\_native\_engine --work build-tmp/windows-engine-build --output build-tmp/windows-engine.


## Unsuccessful jobs

- [Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734): native / windows-11-arm / arm64 (failure). Steps: Installed app creates, searches and reopens a real local workspace.
