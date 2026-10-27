# Automated maintenance status

Observed: 2026-10-27T14:07:42+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.38](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.38). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | queued | [Run 40517759157](https://github.com/Perseusxrltd/mnemion/actions/runs/40517759157) |
| public-updates\.yml | v4\.46\.38 | success | [Run 40505169918](https://github.com/Perseusxrltd/mnemion/actions/runs/40505169918) |
| release\.yml | release/4\.46\.38 | success | [Run 40496801738](https://github.com/Perseusxrltd/mnemion/actions/runs/40496801738) |
| release\.yml | release/4\.46\.39 | success | [Run 40504681891](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891) |
| release\.yml | release/4\.46\.40 | queued | [Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119) |
| verify-artifacts\.yml | main | failure | [Run 40512666290](https://github.com/Perseusxrltd/mnemion/actions/runs/40512666290) |
| website-release\.yml | main | success | [Run 40517759146](https://github.com/Perseusxrltd/mnemion/actions/runs/40517759146) |
| website-release\.yml | v4\.46\.38 | success | [Run 40505165922](https://github.com/Perseusxrltd/mnemion/actions/runs/40505165922) |

## Active jobs

[Run 40517759157](https://github.com/Perseusxrltd/mnemion/actions/runs/40517759157): 1/12 jobs completed; 1 succeeded.

- studio: queued.
- Select checks: in\_progress.
- lint: queued.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- container \(ubuntu-22\.04\): queued.
- service \(3\.14\): queued.
- service \(3\.13\): queued.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.12\): queued.
- legacy: in\_progress.
- container \(ubuntu-22\.04-arm\): queued.

[Run 40518115119](https://github.com/Perseusxrltd/mnemion/actions/runs/40518115119): 0/1 jobs completed; 0 succeeded.

- Release preflight: queued.


## Unsuccessful jobs

- [Run 40512666290](https://github.com/Perseusxrltd/mnemion/actions/runs/40512666290): publish (failure). Steps: Publish unchanged verified assets and dispatch public follow-ups.
