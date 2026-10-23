# Automated maintenance status

Observed: 2026-10-23T18:36:59+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.3](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.3). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (2)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T16:38:46Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40001971973](https://github.com/Perseusxrltd/mnemion/actions/runs/40001971973) |
| public-updates\.yml | v4\.46\.3 | success | [Run 39973022163](https://github.com/Perseusxrltd/mnemion/actions/runs/39973022163) |
| release\.yml | release/4\.46\.3 | success | [Run 39961881757](https://github.com/Perseusxrltd/mnemion/actions/runs/39961881757) |
| release\.yml | release/4\.46\.4 | success | [Run 39997298864](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864) |
| release\.yml | release/4\.46\.5 | queued | [Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734) |
| verify-artifacts\.yml | main | in\_progress | [Run 40004648689](https://github.com/Perseusxrltd/mnemion/actions/runs/40004648689) |
| website-release\.yml | main | success | [Run 40001971952](https://github.com/Perseusxrltd/mnemion/actions/runs/40001971952) |
| website-release\.yml | v4\.46\.3 | success | [Run 39973017198](https://github.com/Perseusxrltd/mnemion/actions/runs/39973017198) |

## Active jobs

[Run 40001971973](https://github.com/Perseusxrltd/mnemion/actions/runs/40001971973): 10/12 jobs completed; 10 succeeded.

- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.12\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734): 5/19 jobs completed; 4 succeeded.

- checks / studio: in\_progress — Check the lightweight native client before six-platform packaging.
- checks / service \(3\.12\): in\_progress — Initialize containers.
- checks / supervision \(macos-15-intel\): queued.
- checks / dependency-audit: in\_progress — Run uvx pip-audit --path \.venv/lib/python3\.12/site-packages.
- checks / service \(3\.13\): in\_progress — Initialize containers.
- checks / legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- checks / container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- checks / container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- checks / supervision \(macos-15\): queued.
- checks / service \(3\.14\): in\_progress — Initialize containers.
- native / Encrypted files / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / Encrypted files / Windows / x64: in\_progress — Run python -m pip install pytest cryptography==50\.0\.2.
- native / native\_database / Private state / Windows / x64: in\_progress — Install small private-state test dependencies.
- native / native\_database / Private state / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.

[Run 40004648689](https://github.com/Perseusxrltd/mnemion/actions/runs/40004648689): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.

