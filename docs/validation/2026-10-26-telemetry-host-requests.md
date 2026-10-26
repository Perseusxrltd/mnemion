# Owned host-request telemetry — 26 October 2026

Current source distinguishes a newly accepted typed host request from replay
before permitting optional desktop/native-operator measurement. The source
checks passed; this is **not installed or live-host acceptance**. Frozen 4.46.15
source `de53ba4609f848f7e91fdc9a8383ded9fb70884f` excludes the addition. V08 stays
**Building**, with production collection/destination/route **false/null/null**
and all **66 requirement texts and states** unchanged.

## Intake disposition and compatibility

The [authority store](../../mnemion/host_control/store.py) returns a request-local
`RequestResult` carrying `new` or `replayed` from the same transaction that
checks authority and records or retrieves the operation. The
[authenticated receiver](../../mnemion/host_control/receiver.py) adds that value
only as `result.request_disposition`. It leaves the protocol-v1 outer envelope,
durable request/result bodies, operation identities and conflict checks unchanged;
no database migration is needed.

The field describes **this intake**, not the age or success of stored work.
Concurrent identical requests yield one `new` and one `replayed` response and
retain one operation. Grant/revoke replays do not repeat authority changes.
Readbacks, refused requests and conflicts carry no fresh-intake marker. Older
replies remain compatible but cannot authorize a measurement without the field.
See the [host response guide](../guides/company-host-control.md#send-requests-and-distinguish-acceptance-from-completion).

## Explicit local ownership

The [desktop-origin map](../../mnemion/product_telemetry/desktop-origins.json)
classifies all 13 typed host commands. Nine mutations have a fixed mapping:

| Typed command | Catalog workflow |
| --- | --- |
| `service.start` | `host.start` |
| `service.stop` | `host.stop` |
| `backup.create` | `backup.create` |
| `backup.verify` | `backup.verify` |
| `upgrade.plan` | `host.plan_upgrade` |
| `upgrade.apply` | `update.apply` |
| `operators.grant` | `host.enroll` |
| `operators.revoke` | `host.revoke` |
| `operations.resolve` | `host.resolve` |

`host.status`, `operations.get`, `operations.list` and `operators.list` are
explicit read exclusions. The [desktop boundary](../../studio/electron/desktop-measurement.ts)
selects only the fixed `request.action`, then requires the host reply's own
`ok: true` and `result.request_disposition: new`. The existing
[dispatcher](../../studio/electron/service-bridge.ts) owns local IPC as `desktop`
and fresh native-operator execution as `native_agent`; cached operator replies
return before execution. The remote receiver and worker acquire no measurement owner.

All selected replies are categorized as **accepted**, not terminal completion of
queued service, backup or upgrade work. A replay, missing/unknown marker, refusal
or lost reply discards the optional submission/outcome pair. No telemetry retry,
lookup or server completion backfill is added. Host/operator/request identities,
keys, paths, arbitrary arguments and result contents never reach the numeric
encoder. Current policy/generation fences and the existing 25 ms optional
snapshot limit remain; unavailable or late privacy reads leave the host action
available without measurement. Mapping names does not qualify every catalog
workflow or complete remote-client coverage.

## Scoped checks and retained failure

The original receiver regression failed once in **0.52 seconds** because
`request_disposition` was absent. That failure is retained. The final selections
completed with zero skips:

| Check | Result and scope |
| --- | --- |
| Python host store, pinned local SSH, server and desktop selection | **47 passed in 21.85 s**; real SQLite transactions, concurrent intake, replay/conflict/refusal, grant/revoke persistence and compatible response envelopes. |
| Node desktop-measurement and host-profile selection | **17 passed in 747.300509 ms**; nine mappings on both owned surfaces, read exclusions, private-value sentinels, legacy/replayed/refused/lost replies and unavailable/late privacy reads. |
| Electron build and Python formatting/Ruff checks | Passed with exit 0. |

The [store regressions](../../service_tests/test_host_control_store.py),
[local SSH regressions](../../service_tests/test_host_control_transport.py) and
[desktop tests](../../studio/electron/scripts/test-desktop-measurement.mjs)
exercise these recorded boundaries. They do not perform real remote-service
actions or establish installed native-matrix, resource, full coverage, utility,
ingress/privacy or production collection acceptance. No new sender, daemon,
timer, identifier or resource experiment is introduced by this batch.

## Original SHA-256 evidence

| Retained evidence | SHA-256 |
| --- | --- |
| Declared plan | `05522323356210d668928a5af4f22f51c55f0115d6b2b8989daa9e6e3d92ced6` |
| Original missing-disposition regression | `1ba03aaa6d8e4111c21e3fda7c1e3c4d7961da892d66b813097e56450d2c704d` |
| Final Python selection | `ac6868b90a4eb88df5c67cfe160d6c70e4b8d04448be13469f1bd0c16a4235c5` |
| Final Node selection | `2a56f0b21f2f27398e9828be4a1fd94022666760ea1fa0b7e43720ed3cd8a7fc` |
| Electron build | `04599f6e1fc955159dad71b6a4140d1a5c5636f50819a8bfe1fc0e3c870e89fb` |
