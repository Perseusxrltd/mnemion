# Release-catalog systemd qualification — 30 October 2026

One isolated local Linux execution of the catalog service passed on source
[`dc7f6c417bf78c9cbded7c6a485b30763bc63dde`](https://github.com/Perseusxrltd/mnemion/commit/dc7f6c417bf78c9cbded7c6a485b30763bc63dde).
The fixture ran from 14:26:27 to 14:26:49 UTC and completed cleanup. It started
no collector or memory service and sent no telemetry reports. Production
collection remains disabled.

The actual [catalog service](../../deploy/collector/mnemion-telemetry-catalog.service)
and [timer](../../deploy/collector/mnemion-telemetry-catalog.timer) used isolated
names, paths and a dedicated non-login account. A measurement command ran in
the same service sandbox before the unchanged catalog CLI. The runtime used
the existing hash-locked wheels; its lock was unchanged. All 461 staged source
and runtime files retained their recorded hashes. Earlier TLS and installed
delivery checks were not repeated.

## Observed result

| Check | Original observation |
| --- | --- |
| Actual synchronization | One matching systemd starting/finished invocation succeeded in 5.206312 seconds. |
| Public catalog | The fixed GitHub source produced a fresh, valid 786-byte local catalog containing releases 4.46.53–4.46.57. |
| Resource restrictions | Actual cgroup limits were 64 MiB RAM, no swap, 10% of one CPU and eight tasks; the service timeout remained 40 seconds. |
| Privileges | Non-root execution, no new privileges, empty effective capabilities and active seccomp; a bind attempt returned `EPERM`. No TLS credential was loaded. |
| Files | State was owned by the dedicated account with mode `0700`; the public catalog had mode `0644`. |
| Scheduling | The real timer was active and waiting, with persistence, daily scheduling, one-hour jitter and 15-minute accuracy. Its recorded next firing was 31 October at 00:03:22 CET. |
| Logging and cleanup | No application stdout entered the fixture journal. Owned units, account, group, timer stamp, state and runtime were removed; no helper process remained. |

The post-exit `ExecMainStartTimestampMonotonic` property was zero. It is not
used as execution or invocation-count evidence: the retained original PID 1
journal records one matching successful invocation, accompanied by the fresh
catalog and sandbox receipt. The private `manifest.json`, `receipt.json`,
`qualification-review.json` and original journal retain that evidence. The
fixture was not rerun.

## Qualification limits

This qualifies local execution and timer scheduling, not a later daily firing,
collector startup or weekly adoption under systemd. The separate
[catalog source checks](2026-10-30-telemetry-live-catalog.md) own their startup,
rollover and fallback coverage. The earlier
[local collector qualification](2026-10-30-telemetry-v3-systemd-local.md) owns
its socket, TLS and credential results.

Public hosting, ingress, provider retention, useful fleet reports and installed
client overhead remain open. The catalog service's resource restrictions are
not measurements of the client overhead budget. The
[disclosure](../../mnemion/product_telemetry/disclosure.json) remains
`collection_available: false` with a null destination; the
[route](../../mnemion/product_telemetry/transport-route.json) remains unset.
All 66 requirement texts and states are unchanged; V08 remains Building.
