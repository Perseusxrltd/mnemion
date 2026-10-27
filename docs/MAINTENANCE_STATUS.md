# Automated maintenance status

Observed: 2026-10-27T14:03:53+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.38](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.38). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 40513098239](https://github.com/Perseusxrltd/mnemion/actions/runs/40513098239) |
| public-updates\.yml | v4\.46\.38 | success | [Run 40505169918](https://github.com/Perseusxrltd/mnemion/actions/runs/40505169918) |
| release\.yml | release/4\.46\.38 | success | [Run 40496801738](https://github.com/Perseusxrltd/mnemion/actions/runs/40496801738) |
| release\.yml | release/4\.46\.39 | success | [Run 40504681891](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891) |
| verify-artifacts\.yml | main | failure | [Run 40512666290](https://github.com/Perseusxrltd/mnemion/actions/runs/40512666290) |
| website-release\.yml | main | success | [Run 40513098255](https://github.com/Perseusxrltd/mnemion/actions/runs/40513098255) |
| website-release\.yml | v4\.46\.38 | success | [Run 40505165922](https://github.com/Perseusxrltd/mnemion/actions/runs/40505165922) |

## Unsuccessful jobs

- [Run 40512666290](https://github.com/Perseusxrltd/mnemion/actions/runs/40512666290): publish (failure). Steps: Publish unchanged verified assets and dispatch public follow-ups.
