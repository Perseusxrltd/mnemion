# Automated maintenance status

Observed: 2026-10-27T01:38:07+00:00. Updated by repository events and the scheduled status workflow.

Published release: [v4.46.29](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.29). [Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).

This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. Build observations cover the latest 100 runs, retaining the latest relevant run per workflow and branch. Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. This automation never retries a build or publishes a release.

## Open issues (1)

| Issue | Report | Last activity |
| --- | --- | --- |
| [#44](https://github.com/Perseusxrltd/mnemion/issues/44) | Integration acceptance: verify the separate Grok Bot cloud client end to end | 2026-10-20T11:20:12Z |

## Relevant builds

| Workflow | Branch | State | Evidence |
| --- | --- | --- | --- |
| ci\.yml | main | in\_progress | [Run 40433638960](https://github.com/Perseusxrltd/mnemion/actions/runs/40433638960) |
| public-updates\.yml | v4\.46\.29 | success | [Run 40423899386](https://github.com/Perseusxrltd/mnemion/actions/runs/40423899386) |
| release\.yml | release/4\.46\.29 | success | [Run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477) |
| release\.yml | release/4\.46\.33 | failure | [Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624) |
| release\.yml | release/4\.46\.34 | in\_progress | [Run 40433580410](https://github.com/Perseusxrltd/mnemion/actions/runs/40433580410) |
| verify-artifacts\.yml | main | skipped | [Run 40430456976](https://github.com/Perseusxrltd/mnemion/actions/runs/40430456976) |
| website-release\.yml | main | success | [Run 40433638922](https://github.com/Perseusxrltd/mnemion/actions/runs/40433638922) |
| website-release\.yml | v4\.46\.29 | success | [Run 40423894613](https://github.com/Perseusxrltd/mnemion/actions/runs/40423894613) |

## Active jobs

[Run 40433638960](https://github.com/Perseusxrltd/mnemion/actions/runs/40433638960): 5/12 jobs completed; 5 succeeded.

- studio: in\_progress — Verify wheel and source package include the matching web Studio.
- legacy: in\_progress — Run uv run --no-sync python -m pytest tests -q --cov=mnemion --cov-config=deploy/legacy\.coveragerc --cov-report=term-missing.
- service \(3\.12\): in\_progress — Matching PostgreSQL recovery tools.
- supervision \(macos-15-intel\): in\_progress — Build the current Intel cryptography runtime with static OpenSSL.
- supervision \(macos-15\): in\_progress — Verify managed installation, host recovery, signed updates and rollback with real processes.
- service \(3\.14\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.
- service \(3\.13\): in\_progress — Run uv run --no-sync python -m pytest service\_tests -q --cov=mnemion --cov-config=deploy/service\.coveragerc --cov-report=term-missing --cov-fail-under=75.

[Run 40433580410](https://github.com/Perseusxrltd/mnemion/actions/runs/40433580410): 8/13 jobs completed; 7 succeeded.

- native / Encrypted files / Windows / arm64: in\_progress — Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1.
- native / native\_database / Database / windows / x64: in\_progress — Relocate, initialize, verify TLS and RLS, restore backup and recover a crash.
- native / native\_database / Database / macos / x64: in\_progress — Run actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803.
- native / native\_database / Database / macos / arm64: in\_progress — Run actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02.
- native / native\_database / Database / linux / arm64: in\_progress — Run actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02.


## Unsuccessful jobs

- [Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624): native / windows-2022 / x64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
- [Run 40426432624](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624): native / windows-11-arm / arm64 (failure). Steps: Run npm --prefix studio/electron test, Retain generated desktop-content secret scan receipt.
