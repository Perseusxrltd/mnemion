# Automated maintenance status

Observed: 2026-10-20T07:35:41+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.33.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.33.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#18](https://github.com/Perseusxrltd/mnemion/issues/18) | OAuth 2\.1 MCP auth so ChatGPT custom connectors can connect \(spec for \#4\) | 2026-10-10T20:58:20Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39382549043](https://github.com/Perseusxrltd/mnemion/actions/runs/39382549043) |
| public-updates\.yml | v4\.33\.0 | in\_progress | [Run 39387468667](https://github.com/Perseusxrltd/mnemion/actions/runs/39387468667) |
| release\.yml | release/4\.33\.0 | success | [Run 39382743155](https://github.com/Perseusxrltd/mnemion/actions/runs/39382743155) |
| verify-artifacts\.yml | main | success | [Run 39387307827](https://github.com/Perseusxrltd/mnemion/actions/runs/39387307827) |
| website-release\.yml | v4\.33\.0 | success | [Run 39387465064](https://github.com/Perseusxrltd/mnemion/actions/runs/39387465064) |

## Active jobs

[Run 39387468667](https://github.com/Perseusxrltd/mnemion/actions/runs/39387468667): 1/7 jobs completed; 1 succeeded.

- macos / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- linux / arm64 public upgrade: in\_progress — Linux desktop libraries.
- linux / x64 public upgrade: in\_progress — Linux desktop libraries.
- windows / x64 public upgrade: in\_progress — Install public release and observe its automatic update.
- windows / arm64 public upgrade: in\_progress — Run python -m pip install psutil==7\.2\.2.
- macos / arm64 public upgrade: in\_progress — Install public release and observe its automatic update.

