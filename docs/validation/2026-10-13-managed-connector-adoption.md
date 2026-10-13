# Existing shared connector adoption — 2026-10-13

The original shared Linux host's Git connector now follows its verified managed
service runtime. This completes the actual-host adoption of the
[4.1.3 lifecycle feature](2026-10-12-managed-connectors.md) for
[issue 22](https://github.com/Perseusxrltd/mnemion/issues/22).

On 12 October, the operator verified the existing runner and process manager,
staged the signed 4.1.4 service package, and prepared a stable connector bootstrap
outside the prunable release slots. The copied runtime was checked against its
verified installation and signed package. The configuration and startup entry
were backed up before the existing entry was changed to managed launch mode.

The prior 4.0.12 runner was stopped only after repeated idle observations. Its
existing process manager started the replacement with the same configuration,
connector identity, provider credential references and source access. The first
managed scan succeeded from the then-current 4.1.1 service runtime. There was
one managed connector registration, not a second source.

The operator then applied the verified compatible **4.1.1 → 4.1.4** service
patch through the normal backup, drain, readiness and recovery machinery. At
**15:54 UTC**, the service was ready with no pending recovery; the next successful
complete scan, launcher and service all reported **4.1.4**. Configuration bytes
were preserved. These were operator actions; automatic enrollment is not claimed.

The actual Windows app independently authenticated to the upgraded service at
15:57 UTC. A fresh read-only check on **13 October at 07:30 UTC** again confirmed
the same saved human administrator and 4.1.4 server, with desktop updates,
background operation and login startup enabled. The installed desktop was 4.1.3;
the initiation of that installation was not observed. These identity checks
made no memory writes or model calls.

The [sanitized observations](2026-10-13-managed-connector-adoption.json) exclude
private endpoints, paths, process identities, credentials and source content.
Normal connector reconciliation did include upstream source changes; it was not
a read-only ingestion exercise. The reported full re-ingestion and inaccurate
managed scan trigger labels remain separately tracked in
[issue 30](https://github.com/Perseusxrltd/mnemion/issues/30).

Unmanaged processes still require explicit adoption, as the
[operator guide](../service/managed-connectors.md) explains. Plain watch mode
reports manual update ownership; managed status exposes launcher and scan
versions. Automatic fleet enrollment, independent host inventory and recovery,
Windows/Compose service policy and company sign-in remain on the roadmap.
