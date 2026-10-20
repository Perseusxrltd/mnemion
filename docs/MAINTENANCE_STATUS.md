# Automated maintenance status

Observed: 2026-10-20T13:51:03+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.39.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.39.0). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (3)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |
| [#45](https://github.com/Perseusxrltd/mnemion/issues/45) | Deployment acceptance: finish guarded host upgrade and expose paused note publishing | 2026-10-20T13:39:27Z |
| [#46](https://github.com/Perseusxrltd/mnemion/issues/46) | Deployment access: Codex/Astra cannot see the existing office task and memory spaces | 2026-10-20T13:38:41Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | success | [Run 39428336656](https://github.com/Perseusxrltd/mnemion/actions/runs/39428336656) |
| public-updates\.yml | v4\.39\.0 | success | [Run 39427237766](https://github.com/Perseusxrltd/mnemion/actions/runs/39427237766) |
| release\.yml | release/4\.39\.0 | success | [Run 39420061069](https://github.com/Perseusxrltd/mnemion/actions/runs/39420061069) |
| release\.yml | release/4\.40\.0 | success | [Run 39424241142](https://github.com/Perseusxrltd/mnemion/actions/runs/39424241142) |
| release\.yml | release/4\.41\.0 | queued | [Run 39428746847](https://github.com/Perseusxrltd/mnemion/actions/runs/39428746847) |
| verify-artifacts\.yml | main | in\_progress | [Run 39433889111](https://github.com/Perseusxrltd/mnemion/actions/runs/39433889111) |
| website-release\.yml | v4\.39\.0 | success | [Run 39427234119](https://github.com/Perseusxrltd/mnemion/actions/runs/39427234119) |

## Active jobs

[Run 39428746847](https://github.com/Perseusxrltd/mnemion/actions/runs/39428746847): 4/18 jobs completed; 4 succeeded.

- checks / studio: in\_progress — Run python deploy/bundle\_studio\.py.
- native / Encrypted files / Windows / x64: in\_progress — Run python -m pip install pytest cryptography==50\.0\.2.
- native / Encrypted files / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Private state / Windows / arm64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Private state / Windows / x64: in\_progress — Install small private-state test dependencies.
- checks / supervision \(macos-15-intel\): in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- checks / legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- checks / container \(ubuntu-22\.04\): in\_progress — Build the actual deployment image with its documentation.
- checks / supervision \(macos-15\): in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- checks / container \(ubuntu-22\.04-arm\): in\_progress — Build the actual deployment image with its documentation.
- checks / dependency-audit: in\_progress — Run uvx pip-audit --path \.venv/lib/python3\.12/site-packages.
- checks / service \(3\.14\): in\_progress — Initialize containers.
- checks / service \(3\.13\): in\_progress — Initialize containers.
- checks / service \(3\.12\): in\_progress — Initialize containers.

[Run 39433889111](https://github.com/Perseusxrltd/mnemion/actions/runs/39433889111): 0/1 jobs completed; 0 succeeded.

- verify: in\_progress — Verify every uploaded byte, production signature and complete feed.

