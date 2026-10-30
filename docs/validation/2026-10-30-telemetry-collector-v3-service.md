# Explicit v3 collector deployment — 30 October 2026

The supplied Linux service previously omitted `--mode`, so following the
service-install instructions started the legacy collector. Current clients use
the separate v3 route. Source based on
`7ee617691ead16c17bbdb9eb797e03f20f186325` now makes the choice explicit without
changing the legacy default or enabling client collection.

The [shared service](../../deploy/collector/mnemion-telemetry.service) sets
`MNEMION_TELEMETRY_MODE=legacy` and passes `${MNEMION_TELEMETRY_MODE}` as one
`--mode` argument. An optional [v3 drop-in](../../deploy/collector/mnemion-telemetry.service.d/v3.conf)
overrides only that variable. There is one shared hardened start command;
account, socket, credentials, sandbox, resource limits and quiet diagnostics
are unchanged. Unsupported modes retain the server's fixed configuration error.

The [operator guide](../implementation/anonymous-product-telemetry-collector.md#deployment-template)
now covers optional v3 installation, inspection, explicit restart of an existing
service and removal of that one drop-in to restore the base default. Legacy
`reports.sqlite3` and v3 `reports-v3.sqlite3` remain separate and are not migrated
or deleted by selecting a mode. A restart still loses the unsealed in-memory
week. The guide distinguishes both formats and supplies the private v3
HTML/JSON/CSV export command. It does not expose a public statistics endpoint.

Actual Grok Build produced the service/drop-in and initial contract check.
Astra reviewed them, removed duplicated command/security literals from the
check, exercised both modes in the same private state directory, and completed
the guide. The bounded Grok job ended at its request limit before a commit or
test run; that limit is not validation evidence.

Three focused checks passed in **5.43 seconds**, with no failures or skips, in
the pinned Linux Python environment:

- The shipped template's default and optional mode select the real collector
  implementations, preserve both stores when switching back, and reject an
  unsupported mode without echoing it or creating state.
- Real loopback TLS accepts the v3 packet on its selected route; the existing
  default still selects legacy. Malformed/cross-route requests retain their
  existing rejection behavior.
- Invalid operator inputs retain fixed errors and do not create a report store.

All four changed source/guide inputs stayed unchanged during the checks. The
template reader validates the shipped literal configuration; it does not run
systemd or qualify a deployed unit. No host, certificate, listener, client
route, disclosure or fleet data changed. No Electron rebuild or native release
was needed for this deployment-template change. Production ingress/retention,
installed report delivery and the 2 MiB / 0.5% client resource gates remain
unaccepted. V08 stays Building, and all 66 requirement states remain unchanged.
