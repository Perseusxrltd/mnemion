# Automated maintenance status

Observed: 2026-10-27T03:47:14+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.35](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.35). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40444411435](https://github.com/Perseusxrltd/mnemion/actions/runs/40444411435) |
| public-updates\.yml | v4\.46\.35 | success | [Run 40444975984](https://github.com/Perseusxrltd/mnemion/actions/runs/40444975984) |
| release\.yml | release/4\.46\.35 | success | [Run 40439256250](https://github.com/Perseusxrltd/mnemion/actions/runs/40439256250) |
| verify-artifacts\.yml | main | success | [Run 40444539230](https://github.com/Perseusxrltd/mnemion/actions/runs/40444539230) |
| website-release\.yml | main | success | [Run 40433638922](https://github.com/Perseusxrltd/mnemion/actions/runs/40433638922) |
| website-release\.yml | v4\.46\.35 | success | [Run 40444972712](https://github.com/Perseusxrltd/mnemion/actions/runs/40444972712) |

## Active jobs

[Run 40444411435](https://github.com/Perseusxrltd/mnemion/actions/runs/40444411435): 9/12 jobs completed; 9 succeeded.

- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

