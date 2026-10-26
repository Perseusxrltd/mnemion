# Native telemetry SQLite cleanup and Windows fixture guard

**Source checkpoint, 26 October 2026.** Native telemetry connections now request
SQLite allocation cleanup before closing. A separate Windows installed-test
guard recognizes version-suffixed installation names. These changes are
**excluded from the already-frozen 4.46.12 candidate**,
source `bd3b212567d878c8b28c1d4c3eb8c86c47bb5311`,
[run 40258369359](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359).
See [release status](../RELEASE_STATUS.md) for evolving availability.

## Source behavior and focused checks

[NativeTelemetryStore.closeDatabase](../../studio/electron/telemetry-store.ts)
requests `PRAGMA shrink_memory` before closing the SQLite connection. Store and
[delivery exits](../../studio/electron/telemetry-delivery.ts) share this cleanup,
including failure paths. If the cleanup request fails, closing is still
attempted; optional telemetry cleanup errors do not propagate into memory work.
The change retains fresh policy checks and does not keep a connection, statement
or positive consent cache alive. Asking SQLite to release reclaimable
allocations does not guarantee a reduction in process RSS.

The actual Electron **44.9.3 / Node 24.22.0** store, delivery and transport
selection passed **44 tests**, with **two Windows-only skips**, zero failures or
cancellations, in **30.8820507 seconds**. The Electron build passed. These are
source/runtime component checks, not installed acceptance across all six targets.

## Small allocation diagnostic

Each retained variant ran once in a separate Electron subprocess using the
native store and synthetic calls. Both completed **241 opens and 241 closes**,
accepted **64 records**, retained a **24 KiB database**, exited successfully and
removed their disposable fixture. Fixture disclosure was enabled locally;
source collection settings were unchanged. Neither run attempted network access.

| Diagnostic variant | Observed ending RSS change |
| --- | ---: |
| Original close behavior (`current`) | 9,531,392 bytes |
| Cleanup before close (`shrink`) | 8,585,216 bytes |

These are mechanism observations, with no representative app workload, memory
operations, TLS or gauges and no forced garbage collection. The single-run
difference is not a causal performance estimate or resource acceptance.
The original diagnostics and earlier
[renderer evidence](2026-10-26-telemetry-renderer-refusals.md) remain preserved.
The later workload observation below does not qualify the unchanged
**2 MiB RSS and 0.5% CPU** targets.

## Later compiled renderer journey

[Run 40260081248](https://github.com/Perseusxrltd/mnemion/actions/runs/40260081248)
completed successfully on 26 October, using changed source
`b9a29886830b63fac75c863e57d55287cc9bd321`. The retained qualification receipt
matched **all 1,961 reviewed source hashes in each of the three compiled
journeys**. This is a later source checkpoint; frozen 4.46.12 source
`bd3b212567d878c8b28c1d4c3eb8c86c47bb5311` remains unchanged.

All three actual development-app journeys ran on Linux x64 with Electron
44.9.3 / Node 24.22.0. Each completed **387 successful real fixture API requests**
(**1,161 total**). The enabled variant recorded **66 writes**, sent one accepted
**four-byte report**, retained nine queue cells and spent one **65,536-byte
reservation**, with its lease cleared and a 24 KiB database. Unavailable and
opted-out variants recorded zero writes and zero reports. Cleanup verified
removal of isolated and certificate profiles, collector shutdown and unchanged
production disclosure.

| Enabled minus unavailable, one sequential comparison | Observation |
| --- | ---: |
| Main-process ending RSS growth | 1,875,968 bytes, below 2 MiB in this observation |
| Main-process sampled-peak RSS growth | 3,440,640 bytes, above 2 MiB |
| Electron CPU difference | 180 ms; 0.2171447873% of one core over the baseline interval |

Ending and sampled-peak growth measure different quantities; the ending value
alone does not pass the memory target. CPU covers Electron processes present at
both boundaries, while external helpers are sampled separately. The 100 ms
sampling interval can miss short-lived children, and RSS sums can count shared
pages more than once. This single comparison does not attribute an improvement
to `shrink_memory` or establish stable resource overhead. The receipt explicitly
keeps **resource acceptance false**. Installed/native-platform, whole-wire and
production privacy acceptance remain open.

## Windows fixture guard

The [installed hosting probe](../../studio/electron/scripts/smoke-installed-hosting.mjs)
now checks `DisplayName -like 'Mnemion Studio*'` before invoking its installer.
A read-only registry query found `Mnemion Studio 4.46.6`, which the previous exact
name equality would miss. The app was **not started or changed**. This guard
protects an existing installation during future diagnostic execution; it is not
a new Windows installed journey, an app-runtime fix, or an explanation for the
[earlier backup-connection timeout](2026-10-26-windows-backup-connection.md).

All **66 requirement texts and states** remain unchanged. V08 is **Building**;
production collection is `false`, with destination and route `null`. Full
resource, installed-platform and production privacy qualification remain open.

## SHA-256 provenance

Original evidence remains private; these hashes identify the inspected files.

| Retained evidence | SHA-256 |
| --- | --- |
| Original-close diagnostic | `896b236ae81fd36b4d8e839f671501a4c80352e960bef5e55f96abd43e7c59ce` |
| Original-close exit receipt | `13ffa812a44ed1a028e171d5bf81d3310e91963330cf5ef790d6f0ecd76deeec` |
| Cleanup-before-close diagnostic | `f6ba9ad798cd851d178fb66bbcd69bf4696b4945409907c97643c20f44adfd68` |
| Cleanup-before-close exit receipt | `cf17adc54db4ee82021d9aff7250e0a6ecbc9481adbbd70dded61ce8f6c26cda` |
| Focused native selection | `16cbd551175e3c3633e4a368f6eda3e30697abf2a2955fb5f39fe84cca298a8e` |
| Focused native exit receipt | `c557395f0688bd46b05020d4f76d3e574e3e2134ba64c5eb6c29c4735d9403f9` |
| Electron build | `b419608b520d806349e9aac310e6d0bb2223824f22ed2d334b1655dc9cda940d` |
| Read-only Windows guard observation | `1116fd8c16819c158652505e4e8cf68a851ecd3ff34474f7c558a1c5e17ec85e` |
| Compiled renderer qualification receipt | `7e6d963d6a1e511dfaf0bb94d68aedecc02af8fda27bc979babb79e33c9a16f0` |
| Original renderer resource summary | `6e6d2554499088549c69cce1699a9918955a6a2e9b08d71ecf7fe1c5c25858d2` |
| Original renderer workload receipt | `2f9a099c118f3d826e46f6e21f64f875b4da1ed09fc3135799ffd1bcf5e8221a` |
| Original renderer cleanup receipt | `1dfdad0691c70f0fcdaad9a0e56f94675038eaccb5de8e0393914569586d75a1` |
