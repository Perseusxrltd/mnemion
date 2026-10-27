# Linux collector crash boundary — 27 October 2026

Source follow-up based on `d26aa9abc201ec6eaa444fc1fba31baf09670e4c`.
The dedicated [collector startup](../../mnemion/product_telemetry/server.py)
now sets Linux `RLIMIT_CORE` soft and hard limits to zero, sets
`PR_SET_DUMPABLE=0`, then requires `PR_GET_DUMPABLE=0`. This precedes taking the
systemd-inherited listener, opening aggregate state and initializing TLS; PID 1
may already hold the socket. Unavailable, denied or still-enabled protection
refuses startup with `telemetry_collector_configuration_invalid`, without private
exception text. The `reports` command and non-Linux execution skip the guard.

The Linux [core manual](https://man7.org/linux/man-pages/man5/core.5.html)
states that `RLIMIT_CORE` is ignored for piped core handlers. The service's
existing `LimitCORE=0` alone therefore does not establish that boundary.
[Process dumpability](https://man7.org/linux/man-pages/man2/PR_SET_DUMPABLE.2const.html)
is a separate kernel control; this startup check does not control privileged
host or provider snapshots.

Six original regression cases are retained: the real child remained dumpable, and
five injected load/limit/set/read/still-enabled failures did not refuse startup.
The corrected [collector tests](../../tests/test_product_telemetry_collector_server.py)
passed **19 distinct cases in 29.21 seconds**, with no failures or skips; Ruff
lint and format checks passed. The child probe reads actual kernel settings but
replaces serving. Existing tests separately exercise real TLS and an inherited
socket, including bounded handshake, header and stalled-connection handling.
No crash or core capture was triggered. The minimal runtime was Python 3.12.3,
Uvicorn 0.54.0, h11 0.16.0 and Click 8.5.0; no dependencies were installed.

All **439 runtime/test/lock inputs** matched before and after the checks,
with manifest digest
`932d39b992ff7eb85d1251963c304686f67f61eb68ee059ebe2830c6b2596355`.
Retained `source-qualification.json` SHA-256:
`81e15f4a4c4593e390590282309f5c2bce557b08a7b6ed0215072b5f290577b6`.
The original six-failure log remains unchanged (SHA-256
`aea313ec9a3cb0a7b53e502470ce09011e183eb73fca52ce3f8569c24e8b18e0`).

Bounded read-only host metadata found a non-piped core pattern and absent
collector service/socket units. The observed dumpable value `1` and core limits
`[0, -1]` belonged only to that read-only probe; defaults reported for absent
units are not installed collector settings. These observations establish
neither an installed collector nor a current data leak. No network logs, dumps,
private keys, credentials or backup contents were read, and no host settings
were changed.

Actual crash handling, non-Linux behavior, installed service restrictions,
provider/log/backup privacy and resource acceptance remain open. No deployment,
activation or app/resource comparison occurred. The
[V08 acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) preserves all
66 requirements, V08 **Building**, production collection/destination/route
**false/null/null**, empty release CAs and the **2 MiB / 0.5%** resource ceilings
with all earlier failed evidence.

The later [serving-process crash checks](2026-10-27-telemetry-collector-crash.md)
extend this historical source checkpoint: the full file passed 21 cases,
including two actual Linux/WSL2 TLS-process crashes with kernel `CLD_KILLED`
and no canary in retained collector state. The existing runtime guard was unchanged.
This adds scoped Linux crash evidence; installed/non-Linux and production
host/provider retention remain unqualified.
