# Automated maintenance status

Observed: 2026-10-27T02:38:33+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.34](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.34). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40430021395](https://github.com/Perseusxrltd/mnemion/actions/runs/40430021395) |
| public-updates\.yml | v4\.46\.34 | in\_progress | [Run 40439538705](https://github.com/Perseusxrltd/mnemion/actions/runs/40439538705) |
| release\.yml | release/4\.46\.34 | success | [Run 40433580410](https://github.com/Perseusxrltd/mnemion/actions/runs/40433580410) |
| release\.yml | release/4\.46\.35 | in\_progress | [Run 40439256250](https://github.com/Perseusxrltd/mnemion/actions/runs/40439256250) |
| verify-artifacts\.yml | main | success | [Run 40438996406](https://github.com/Perseusxrltd/mnemion/actions/runs/40438996406) |
| website-release\.yml | main | success | [Run 40430021427](https://github.com/Perseusxrltd/mnemion/actions/runs/40430021427) |
| website-release\.yml | v4\.46\.34 | success | [Run 40439536199](https://github.com/Perseusxrltd/mnemion/actions/runs/40439536199) |

## Active jobs

[Run 40439538705](https://github.com/Perseusxrltd/mnemion/actions/runs/40439538705): 1/7 jobs completed; 1 succeeded.

- linux / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 40439256250](https://github.com/Perseusxrltd/mnemion/actions/runs/40439256250): 14/15 jobs completed; 13 succeeded.

- native / Service engine / Windows x64: in\_progress — Run uv sync --locked --no-default-groups --group native-build --python 3\.13 --no-managed-python.

