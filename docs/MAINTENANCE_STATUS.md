# Automated maintenance status

Observed: 2026-10-26T21:23:26+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.27](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.27). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40385484447](https://github.com/Perseusxrltd/mnemion/actions/runs/40385484447) |
| public-updates\.yml | v4\.46\.27 | in\_progress | [Run 40403841976](https://github.com/Perseusxrltd/mnemion/actions/runs/40403841976) |
| release\.yml | release/4\.46\.27 | success | [Run 40391018946](https://github.com/Perseusxrltd/mnemion/actions/runs/40391018946) |
| release\.yml | release/4\.46\.28 | in\_progress | [Run 40399013490](https://github.com/Perseusxrltd/mnemion/actions/runs/40399013490) |
| release\.yml | release/4\.46\.29 | pending | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| verify-artifacts\.yml | main | success | [Run 40402981613](https://github.com/Perseusxrltd/mnemion/actions/runs/40402981613) |
| website-release\.yml | main | success | [Run 40385484524](https://github.com/Perseusxrltd/mnemion/actions/runs/40385484524) |
| website-release\.yml | v4\.46\.27 | success | [Run 40403837950](https://github.com/Perseusxrltd/mnemion/actions/runs/40403837950) |

## Active jobs

[Run 40403841976](https://github.com/Perseusxrltd/mnemion/actions/runs/40403841976): 1/7 jobs completed; 1 succeeded.

- linux / x64 public upgrade: in\_progress — Linux desktop libraries.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 40399013490](https://github.com/Perseusxrltd/mnemion/actions/runs/40399013490): 15/21 jobs completed; 14 succeeded.

- native / windows-2022 / x64: in\_progress — Run npm --prefix studio/electron test.
- native / macos-15-intel / x64: in\_progress — Run uv run --project studio/client --no-sync python -m pytest client\_tests -q.
- native / ubuntu-22\.04-arm / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / windows-11-arm / arm64: in\_progress — Select the service interpreter independently of the desktop client.
- native / macos-15 / arm64: in\_progress — Package the native desktop with one bounded upstream-download retry.
- native / ubuntu-22\.04 / x64: in\_progress — Package the native desktop with one bounded upstream-download retry.

