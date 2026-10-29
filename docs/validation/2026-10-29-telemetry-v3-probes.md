# Qualification probes on the v3 contract — 29 October 2026

The actual-app probe listeners now use `CollectorV3` and `POST /v3/report`.
`wire-v3.json` fixes the packet at 25 bytes. Manual review retains a body only
when that body is exactly one 25-byte synthetic packet. A shorter prefix, a
longer body, or any non-review run keeps no body. Preference setup uses
`policy.DISCLOSURE_VERSION` from the release disclosure. That value is 1 in
the current disclosure file; the probes no longer type the old approval number
themselves.

New diagnostic receipts record `wire_version` 3, `/v3/report`, and
`packet_bytes` 25. The summary reader labels a receipt that has none of those
fields `historical-v2` and keeps it on the 4-byte `/v1/report` contract. A
receipt that mixes the two is rejected. Nothing here reinterprets an old
resource comparison as v3. `resource_acceptance` stays false. The optional
nine-phase counters and the ordinary-mode `None` result are unchanged.

This does not qualify the client integration that is still being wired. No app,
browser, or installed run was executed for this note. Production collection,
destination, and route stay false/null/null. V08 remains Building. The 2 MiB
and 0.5 percent gates, and every earlier resource failure, stay failed.
