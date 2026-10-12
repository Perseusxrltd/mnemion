# Idle model cleanup validation — 2026-10-12

Published version: **4.1.1**. Product checks
and the real-model Linux/Intel Mac/Apple Silicon matrix passed in
[run 38218635340](https://github.com/Perseusxrltd/mnemion/actions/runs/38218635340).
All six native installer/update gates, independent artifact/signature verification
and all six public-feed upgrades also passed; see the
[publication record](2026-10-12-model-idle-release.md).

The API and long-running indexing worker each start one idle-cache monitor.
After 300 seconds without inference, it releases inactive local sessions while
preserving model files, generation fingerprints and canonical data. The existing
inference gate protects active and queued work. Operators can disable cleanup
or choose 10–86400 seconds. This does not combine API and worker peak allocations
or impose a whole-host memory limit.

Local validation passed:

- 49 focused resource, inference, cleanup and authenticated-insights tests.
- The full service suite completed with 568 passes and seven opt-in skips.
  Five environment failures were rerun successfully: the managed-service test
  needed the pinned `uv` executable; four recovery tests needed more headroom
  than the deliberately restricted 512 MiB test process had available. The
  five-test rerun used 768 MiB and passed, without changing production checks.
- Nine TypeScript client tests and both web and desktop frontend builds.
- Repository lint, formatting, release-version validation and whitespace checks.
- A real browser with an isolated PostgreSQL workspace displayed the default
  300-second policy and running monitor. Screens at 1440 and 390 pixels had no
  horizontal overflow. Removing the optional `model_cache` response verified
  compatibility with older servers; restoring it restored the panel. No browser
  errors occurred during those checks. The disposable workspace used a
  deterministic embedder, not production data or a model-quality benchmark.

The opt-in real-model tests now measure resident memory before loading, after
loading, after actual background eviction and after an offline reload for both
pinned CPU profiles. They verify the same vectors, Unicode source spans and
fingerprints survive. Linux and both Mac CI jobs preserve numeric reports.
The [numeric observations](2026-10-12-model-idle-measurements.json) were inspected.
All six model/platform pairs passed background eviction, offline reload, vector
and source-span preservation, and monitor shutdown. These are process RSS
samples from the service test suite, including earlier tests and allocator
retention; they are not clean-process minimum hardware requirements.

| Test platform | Profile | Loaded → after idle, MiB | Offline reload/query, ms |
| --- | --- | --- | --- |
| Linux x64 | E5 small | 931.6 → 839.0 | 609.12 |
| Linux x64 | BGE small | 839.0 → 839.0 | 162.22 |
| macOS ARM64 | E5 small | 903.6 → 727.3 | 811.22 |
| macOS ARM64 | BGE small | 747.7 → 747.7 | 135.53 |
| macOS x64 | E5 small | 647.3 → 290.7 | 1602.42 |
| macOS x64 | BGE small | 313.2 → 274.8 | 350.41 |

Releasing sessions does not guarantee an immediate RSS decrease: the BGE cases
on Linux and Apple Silicon showed little or none in this run. API/worker peak
duplication and broader hardware measurements remain open under
[issue 13](https://github.com/Perseusxrltd/mnemion/issues/13).

The current published release is [4.1.1](2026-10-12-model-idle-release.md).
See the [resource controls](../service/memory-resources.md) and
[4.1.1 release notes](../releases/4.1.1.md).
