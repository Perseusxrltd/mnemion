# Idle model cleanup validation — 2026-10-12

Source version: **4.1.1**. Native release and real-model acceptance are pending.

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
Their results must be inspected before claiming measured savings or declaring
the release ready. Allocator behavior and reload latency vary by platform.

The current published release remains [4.1.0](2026-10-12-v410-release.md).
See the [resource controls](../service/memory-resources.md) and
[4.1.1 release notes](../releases/4.1.1.md).
