# Reusing a confirmed opt-out as a negative hint — 27 October 2026

This source follow-up is based on
`3f06d70b70f86365307e5837622ee594574d5025`. Two original regressions are retained:
a confirmed disabled control reply supplied no callback, and the next native
workflow snapshot opened SQLite again despite that confirmed opt-out. The
corrected focused case records **zero additional native SQLite opens**, with
the saved choice and empty preview unchanged. This is an operation count, not
an RSS or CPU measurement.

The [control boundary](../../studio/electron/product-telemetry.ts) notifies only
after a successful `status` or `configure` reply with `schema_version` exactly
`1`, `user_enabled` exactly `false`, and no aborted request. Effective disablement
alone, malformed flags, other schema versions and schema inspection do not
supply the hint. Callback failure preserves the original control result.

The [bridge](../../studio/electron/service-bridge.ts) retains only the monotonic
deadline set when that reply arrives. An existing or later-created owner receives
the same deadline; delayed construction cannot start a fresh 60-second lifetime.
The [native store](../../studio/electron/telemetry-store.ts) binds the hint to its
existing file/day checks, **250 ms** file-observation interval and expiry of at
most **60 seconds**. Invalid, expired or excessive deadlines are rejected. A stale
hint can only suppress optional samples until invalidation or expiry; it cannot
authorize collection, reservation or final handoff.

Installing the hint adds no SQLite read, worker, timer, sideband file or network
request. It does not replace any fresh collection/write, consent, generation,
reservation or final-send authority check. Unavailable builds create no store
through this path.

## Scoped validation

The six-script group ran in actual Electron with `ELECTRON_RUN_AS_NODE=1` and the
real Python helper: **118 tests total, 116 passed, zero failed and two Windows-only
skips**, in **45.83 seconds**. Control/store tests cover the callback, duplicate
read, original expiry, re-enable/file recreation, invalid deadlines and unchanged
write fences; cold-start, delivery, reservation, owner and real TLS checks also
passed. SDK and native builds passed. The original two failing regressions remain
retained. An earlier dependency-reuse attempt failed before linking modules
because checkout was incomplete; it remains a separate setup failure.

All **623 runtime/test inputs** were verified unchanged after testing, with
inventory digest
`9ae130b3114baf3409834623f68940291a276b243e6e6b04407d07820a4cb9d7`.
The retained native test log has SHA-256
`66c65ffd3f5c0165977e18c22045bab02286a06e06cc5f0b1be23800a5dadbf1`.
The regenerated inventory has unchanged rows: **700 total, 396 mapped, 294
excluded, eight delegated and two unmeasured**.

This qualifies a native source component, not an installed app/platform journey,
enabled-mode optimization or measured resource saving. No new app comparison is
selected. All [earlier resource failures](2026-10-27-telemetry-delivery-comparison.md)
and the strict **2 MiB / 0.5%** ceilings remain binding. The
[acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) retains the full
privacy, wire, resource, platform and release gates. All 66 requirements remain
unchanged; V08 stays **Building**, collection/destination/route **false/null/null**,
with empty release CAs.
