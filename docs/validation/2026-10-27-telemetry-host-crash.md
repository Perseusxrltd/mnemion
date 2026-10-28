# Collector host crash and restart qualification — 27 October 2026

A fresh, temporary collector service on the existing Hostinger VPS qualified the
current source's **IPv6 loopback systemd handoff, crash disposition and automatic
restart**. It listened only on `::1`, using kernel `6.8.0-147-generic` and systemd
255. The host core handler was **not piped**, unlike the earlier local WSL2 crash
fixtures. The production collector was not enabled and the canonical memory
service was unchanged.

The actual service accepted one automatic wire-v2 packet over TLS. An owned
pidfd then delivered `SIGABRT` while a synthetic private TLS request was incomplete.
Systemd recorded `ExecMainCode=2` and `ExecMainStatus=6`, indicating signal
termination without a kernel core dump. Exactly **one automatic restart** followed;
the restarted service accepted one reviewed wire-v2 packet. Session tickets were
disabled and responses contained no private canary.

The existing service restrictions were retained. All **eight sandbox checks**
passed: IPv4/IPv6 `connect` and `bind` were denied, privileges could not increase,
capabilities were empty, seccomp was active and the process was unprivileged.
The cgroup enforced 128 MiB memory, zero swap, 25% of one CPU and 16 tasks;
the service descriptor limit remained 128. These are service limits, not a
measurement or qualification of client telemetry overhead.

The **original controller still failed with exit 1** at final report inspection.
Its scrubbed `PATH=/bin:/usr/bin` could not find `runuser`, available at
`/usr/sbin/runuser`, so the reports command had not run. The original failed receipt and successful process/
listener cleanup remain intact. A separate retained-state inspection used the
absolute executable and ran the reports command for the first time. It started
no service and repeated no crash.

That inspection passed and returned `{"schema_version":1,"reports":[]}`. The
8,192-byte database was byte-unchanged; state/database modes were `0700`/`0600`.
The test units had 13 lifecycle journal records, zero stdout records and no
private canary. All test processes were stopped and the IPv6 port was released.
This qualifies the bounded service checks and retained-state inspection; it does
not rewrite the original controller result as a pass.

The deployed manifest verified **437 source inputs**, based on
`3f8718688f9f8712906d1b88971323e438f041e0`, with digest
`92fd0359c49d1945a00f78d27e1297850f69e5015a4b63154df8c796894d8947`.
The [36-pass local IPv6 selection](2026-10-27-telemetry-ipv6-collector.md) retains
its unchanged 435-input digest
`1236cebf962a00092cae5b6b942a0aced1416d4fa7f2f920d2e295aad93f4a73`.
The original host qualification receipt SHA-256 is
`5f7d1094dbf12953edde5d70bf279678b15654a085ea8dbcc2834407c1f43bed`;
the closed assessment SHA-256 is
`809509a2ca4fb38321a8580b743a06ad6d473db28d3db5db9ec01cb9e7374b59`.
Host identity, operational paths and raw journal contents remain private.

This is collector source qualification for main, with no separate native release
for this unavailable collector-only follow-up. The existing 4.46.42 release remains
immutable; later cumulative releases can include the source. All 66 requirement
states and **V08 Building** remain unchanged. Collection/destination/route remain
**false/null/null**, with empty release authorities. The
[failed RAM comparison](2026-10-27-telemetry-sql-comparison.md), strict 2 MiB / 0.5%
ceilings, public ingress/provider logging and snapshots, whole-wire, installed/
all-platform and full telemetry acceptance remain open. No production activation,
telemetry completion notification or email follows from this qualification. See the
[collector contract](../implementation/anonymous-product-telemetry-collector.md)
and [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md).
