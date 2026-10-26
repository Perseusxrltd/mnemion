# Telemetry storage ownership slot — 26 October 2026

New source bounds concurrent native SQLite handles and Windows permission
helpers. It follows the [storage ownership review](2026-10-26-telemetry-storage-ownership.md)
and is excluded from frozen 4.46.14 source
`a5e574a9676ab724141b024d9ac1bb795ef1a688`. V08 remains **Building**,
collection/destination/route remain **false/null/null**, and all 66 requirement
states are unchanged.

## Reproduced handle overlap

The [real SQLite regression](../../studio/electron/scripts/test-telemetry-store.mjs)
offered one burst of 32 snapshot calls across two `NativeTelemetryStore`
instances. Before the fix, asynchronous callers opened their connections before
their callers resumed to close them. The original failing assertion and result
remain preserved.

| Same 32-call diagnostic | Before | After |
| --- | ---: | ---: |
| Successful snapshots | 32 | 1 |
| Peak live SQLite handles | 32 | 1 |
| Handles remaining after the burst | 0 | 0 |

A later independent snapshot and record succeeded after the guarded burst.
[NativeTelemetryStore](../../studio/electron/telemetry-store.ts) now claims one
process-wide slot before asynchronous permission or SQLite work. Competing
optional work declines without waiting or queueing. Only the owning call can
release the slot, after actual connection closure; an unclosed or uncertain
handle keeps it occupied. A failure before opening releases only its own claim.

This slot belongs to the Node/Electron process. Shared private SQLite
transactions still coordinate Python and other processes. Fresh permissions,
policy, company restrictions, generation/revision, spending and final-handoff
checks remain; no positive permission cache or persistent telemetry service is
introduced.

## Helper and control lifetime

[WindowsTelemetryPrivateProbe](../../studio/electron/telemetry-private-store.ts)
retains one helper until actual process exit, including after its one-second
refusal deadline or an error with a live PID. Requesting a kill does not free
ownership. Competing calls decline rather than reuse another path's permission
result; failed launches and stale callbacks cannot clear a successor's claim.
The native executable and its arguments are unchanged.

[Privacy refresh](../../studio/frontend/src/workspace/Privacy.tsx) now takes
status and review state from one coherent `review_status` response, removing
the second native control request. Previous previews are still cleared and
late responses discarded. The frontend build passed in 25.022 seconds.

## Source checks and limits

The native storage/delivery/transport selection passed **49 tests**, with
**two Windows-only skips** (**51 total**, 15.381 seconds), including real
loopback TLS, opt-out and final handoff. **Five helper lifecycle tests passed**
in 1.116 seconds using controlled `ChildProcess` events; they are not actual
Windows installed-helper qualification. Both Electron builds passed.

| Original evidence | SHA-256 |
| --- | --- |
| Original failing concurrency diagnostic | `a7772ee9f65f6e1421b12d407f54b585165bc1fff9a8ad9dcba522720886f8ef` |
| Native selection and corrected diagnostic | `7962d19a14ba9b868eaefc529f11b6d61493714c072758a0074d63ebfe8028ac` |
| Helper lifecycle checks | `4828b27487c6fd4df4cb16ed6b2c1a46306f6a7fd9df321b1650daf591231a23` |
| Electron build logs, identical content | `3e8d4a7fbeca9c61c7ac95b99ec338b148ef89dab5a1c4eca9aec5e8ac6d4e25` |
| Frontend build log | `b6f6f7c19b16515391992dc99bb6584eb16bcffdd97caf9f1f8662428896dd2b` |

This is a connection/lifetime diagnostic, not a renderer benchmark. It does
not establish that overlap caused the earlier 3.6 MiB RSS difference, nor that
the new source meets the unchanged **2 MiB / 0.5%** gates. No renderer run was
dispatched. Original attribution outcomes remain valid; full resource, privacy,
utility and installed/platform acceptance remain open.
