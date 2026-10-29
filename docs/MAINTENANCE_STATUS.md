# Automated maintenance status

Observed: 2026-10-29T02:46:23+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.47](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.47). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#47](https://github.com/Perseusxrltd/mnemion/issues/47) | Field report \(4\.46\.40\): multi-agent usage audit — slow/hanging search, suspended connector scope, noisy activity log, unusable vault over MCP, and features left unused | 2026-10-28T17:01:24Z |
| [#48](https://github.com/Perseusxrltd/mnemion/issues/48) | Mnemion as the single system: full replacement of LEDGER/DISPATCH/files, plus vault compatibility | 2026-10-28T09:04:09Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40792613991](https://github.com/Perseusxrltd/mnemion/actions/runs/40792613991) |
| public-updates\.yml | v4\.46\.47 | in\_progress | [Run 40808263819](https://github.com/Perseusxrltd/mnemion/actions/runs/40808263819) |
| release\.yml | release/4\.46\.47 | success | [Run 40801649181](https://github.com/Perseusxrltd/mnemion/actions/runs/40801649181) |
| release\.yml | release/4\.46\.48 | in\_progress | [Run 40806507811](https://github.com/Perseusxrltd/mnemion/actions/runs/40806507811) |
| verify-artifacts\.yml | main | success | [Run 40807818311](https://github.com/Perseusxrltd/mnemion/actions/runs/40807818311) |
| website-release\.yml | main | success | [Run 40792614050](https://github.com/Perseusxrltd/mnemion/actions/runs/40792614050) |
| website-release\.yml | v4\.46\.47 | success | [Run 40808260569](https://github.com/Perseusxrltd/mnemion/actions/runs/40808260569) |

## Active jobs

[Run 40808263819](https://github.com/Perseusxrltd/mnemion/actions/runs/40808263819): 1/7 jobs completed; 1 succeeded.

- windows / x64 public upgrade: in\_progress — Run python -m pip install psutil==7\.2\.2.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / x64 public upgrade: in\_progress — Linux desktop libraries.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.

[Run 40806507811](https://github.com/Perseusxrltd/mnemion/actions/runs/40806507811): 11/14 jobs completed; 10 succeeded.

- native / native\_database / Database / linux / x64: in\_progress — Compile pinned PostgreSQL, vector extension and static libraries.
- native / native\_database / Database / windows / x64: in\_progress — Compile pinned PostgreSQL, vector extension and static libraries.
- native / Service engine / Windows x64: in\_progress — Run uv run --no-sync python -m deploy\.build\_native\_engine --work build-tmp/windows-engine-build --output build-tmp/windows-engine.

