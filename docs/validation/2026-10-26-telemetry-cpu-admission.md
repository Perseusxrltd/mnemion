# Bounded desktop CPU admission

**Source change, 26 October 2026; excluded from published 4.46.13.** Desktop
telemetry can read aggregate CPU counters without constructing per-core model,
speed and timing objects on Linux and macOS. Windows retains the existing Node
sensor. Collection remains unavailable; the unchanged **2 MiB added RSS and
0.5% of one core** limits are not accepted by this component work.

## Allocation mechanism and implementation

The [completed six-case attribution](2026-10-26-telemetry-attribution.md) required
an initialization/storage review before another experiment. Inspection of the
bundled Node 24.22.0 sources identified a concrete avoidable allocation:
[Linux `uv_cpu_info`](https://github.com/nodejs/node/blob/v24.22.0/deps/uv/src/unix/linux.c)
allocates 8,192 entries of a 56-byte scratch structure, or **458,752 bytes per
call**, before allocating per-core results and CPU model strings.
[`os.cpus()`](https://github.com/nodejs/node/blob/v24.22.0/lib/os.js) also creates
per-core JavaScript objects. Desktop admission uses only idle time, total time
and processor count. It takes two readings at least 250 ms apart during an
eligible, already-awake attempt; it adds no idle sampler.

The existing [native helper](../../mnemion/product_telemetry/native/network-state.c)
now exposes an aggregate C ABI and a three-number Node result. Linux reads only
the first `/proc/stat` line into a **512-byte stack buffer**. It retains the
previous user/nice/system/idle/IRQ sum, excluding iowait and later columns.
macOS uses the fixed `host_cpu_load_info` result and releases the acquired Mach
port. Counters and CPU count remain process-local admission inputs, never
outgoing measurements or hardware profiles.

The [Windows Node implementation](https://github.com/nodejs/node/blob/v24.22.0/deps/uv/src/win/util.c)
adds IRQ time separately from kernel-minus-idle. `GetSystemTimes` alone would
change that idle fraction, so the Windows helper reports unavailable CPU totals
and keeps the existing Node fallback. Older, missing or unreadable helpers also
retain that fallback on every platform.

The [desktop reader](../../studio/electron/telemetry-cpu.ts) rejects malformed,
overflowing or inexact counters. The [admission owner](../../studio/electron/telemetry-conditions.ts)
requires two fresh comparable readings after an unknown sample, counter reset,
provider or processor-count change, long idle gap, read error or clock rollback.
At least 20% measured idle time is still required; network, thermal, available
memory and user/company restrictions remain separate vetoes.

The storage review also found that upstream Node's
[`DatabaseSync::Close`](https://github.com/nodejs/node/blob/v24.22.0/src/node_sqlite.cc)
already finalizes statements and deletes sessions before closing SQLite. This
change adds no further SQLite close calls or retained connections. The upstream
source review is not proof of exact parity with every Electron patch.

## Validation and limits

The Electron/native build passed. **54 Python checks** passed, including actual
Linux C ABI use, parser bounds, overflow rejection and existing network
restrictions. **16 final Node admission checks** passed, including valid-native
fallback avoidance, missing/invalid support, busy/reset readings and recovery.
The existing **15 TLS transport checks** passed, including opt-out, cancellation,
deadline and route restrictions. The first combined run retained one failing
test-clock fixture: it advanced synthetic time without letting the independent
network refresh complete. The corrected fixture gives that refresh its normal
event-loop turn; no production freshness rule or timeout was relaxed.

An actual Linux x64 component probe under **Python 3.12.3 and Electron
44.9.3 / Node 24.22.0** confirmed the aggregate ABI in both runtimes. The native
module SHA-256 was
`2eea0dc8957b596f3f7b4bb4c4ce23bb05caef8a5daea1b975da5de8a33c2415`.
Its observed Electron RSS increase was **2,883,584 bytes**, above 2 MiB.
This probe includes module activation, network flags and one aggregate CPU
reading; its new `probe_scope` distinguishes it from earlier network-only
observations. It is not an installed or full-feature resource measurement and
does not prove a causal RSS reduction.

No renderer workload was dispatched for this change. All six original
attribution outcomes remain preserved. Native macOS qualification of the new
CPU path, representative full-platform resource and wire measurements, exact
outgoing-packet inspection and production ingress/privacy qualification remain
open. The already published [4.46.13 native receipts](2026-10-26-44613-native-acceptance.md)
cover the earlier source, not this CPU change or completed V08.
