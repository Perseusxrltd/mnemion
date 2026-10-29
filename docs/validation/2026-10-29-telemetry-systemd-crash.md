# Systemd collector crash and restart — 29 October 2026

An isolated Linux systemd fixture completed **six recorded checks** between
**00:58:29 and 01:00:45 UTC**, followed by an independent cleanup check at
**01:03 UTC**. It used source
`772f5c0bf7f007e2006e35763d659797a4780497`, with **440 source files**
verified against the same locked archive used for the
[systemd certificate-rotation qualification](2026-10-28-telemetry-systemd-rotation.md).
Collector code was unchanged.

The fixture used the repository [service](../../deploy/collector/mnemion-telemetry.service)
and [socket](../../deploy/collector/mnemion-telemetry.socket) templates, retaining
the static service account, sandbox and `Restart=on-failure` policy. Only the
fixture's source/runtime/state/credential locations and loopback listener
address/port were substituted. The certificate and reports were synthetic;
there were no issuer requests, public listeners or changes to global kernel
settings or client collection.

## Observed process and recovery

The six records include initial credential preparation; **one** controlled
crash was induced between the two completed requests.

| Recorded check | Result |
| --- | --- |
| Service-account import | The collector module imported under the existing static service account. |
| Initial bundle | Credential preparation returned `changed: true` and `activation: "not_requested"`. |
| Serving collector | Systemd reported an active process. Its certificate matched the prepared bundle, and a four-byte synthetic report returned HTTP 204 with an empty body over the loopback-only listener. |
| Process protection | Both core-file limits were zero, and the checked process descriptor directory was root-owned. The host's existing `core_pattern` selected a file handler. |
| Owned-process crash | A pidfd pinned the collector process; its active unit/PID were rechecked before one `SIGABRT`. Systemd recorded `ExecMainCode=2`, `ExecMainStatus=6` and `Result=signal`, indicating signal termination without the kernel core-dump flag. No new core-named file appeared in the fixture source directory, and no matching `COREDUMP_PID` journal record was found. |
| Configured automatic recovery | Systemd started a new active PID and reported `NRestarts=1`. The restarted collector presented the expected certificate and accepted a second four-byte report with HTTP 204. No operator restart was requested. |

After stopping both fixture units, the one report database contained **zero
completed-window reports**. That observation concerns the fixture's report
table; it does not audit provider snapshots, unrelated logs or general retention.

The host used a **file-based**, not piped, core handler. The earlier
[WSL serving-process crashes](2026-10-27-telemetry-collector-crash.md) exercised
a piped handler without installing systemd units. The
[earlier IPv6 host qualification](2026-10-27-telemetry-host-crash.md) retains
its separate source, checks and original controller failure. These evidence
scopes remain distinct.

## Cleanup and evidence binding

The fixture's cleanup passed. Independent inspection confirmed the temporary
units, runtime and state were absent. The existing memory service kept the
same PID, and the Certbot timer remained active and waiting. Production
collector units were absent before the fixture and after cleanup.

The retained qualification binds the following original artifacts. Private
host details, operational paths, environment and key material are excluded
from this report.

| Artifact | SHA-256 |
| --- | --- |
| Source/runtime archive, shared with the rotation fixture | `2cfb88765da6fb6a3d0799fa6be7dcb0e46d4abb497e87875d1a8a75e502a5a7` |
| Crash fixture script | `c7d82265c77a14381c821e7fa0f0a2fa878d8fdb68c80d458db1388a6f1848ba` |
| Host result | `5870039c80b6b3f4cf029923914401a45556dbedaa026247009353224d95c4a9` |
| Independent cleanup result | `99e94c00dde5626899977582171c9524e3431a827351d332ecfceb9fb2fc4d48` |
| Qualification receipt | `773d6bbcce0f2a5a9b0bdfb19a2e22767aa98c3bfd96f104d6bab9be48b9ebb4` |

## Remaining acceptance

This qualifies the stated isolated Linux systemd crash protection and
configured restart. It supplies no client resource measurement, whole-wire
bound, public ingress/provider qualification or installed-platform/workflow
coverage. Broader privacy and useful-aggregate acceptance remain open.

V08 remains **Building**, with production collection/destination/route
**false/null/null** and empty release CAs. All **66 requirements** and budgets
remain unchanged, including the **2 MiB / 0.5%** resource limits. The
[acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) retains the
remaining work; this component result does not establish full telemetry
completion.
