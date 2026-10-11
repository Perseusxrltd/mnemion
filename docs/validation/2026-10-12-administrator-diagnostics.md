# Administrator connection checks and version visibility

Validation date: **2026-10-12**. Candidate: **4.0.13**. Public downloads remain
governed by the release gates; source validation alone is not publication.

## Reproduced failure

The [original workspace backup](2026-10-12-encrypted-workspace-backup.md) was
restored into a separate database and migrated using the signed, verified 4.0.12
runtime. Managed setup successfully started its API, worker and updater and
verified their private initialization receipts. However, the released connection
doctor reported `invalid_response` for `/v1/spaces` with HTTP 200 and skipped MCP.

An organization administrator can list compartments without having permission
to read their memories. The API correctly represents these as `role: null`.
The doctor incorrectly required a non-null role for every visible compartment.
The recovered owner saw three compartments but held a content grant in only one.

## Correction and verification

The doctor now accepts the contract's explicit null role, preserves the visible
`count`, and reports a separate `accessible_count` plus a histogram of granted
roles. No grants still produces `no_spaces`; authenticated MCP checks continue.
Missing, malformed and unknown roles remain invalid. No permission changes are
made to pass a diagnostic.

Three new positive/empty-scope regression cases failed before correction.
After correction, **38 diagnostic and client tests** passed, including real
PostgreSQL/API/MCP tests of independent administrators with and without a content
grant. The earlier **40 targeted service/administration/client checks** and
**nine TypeScript client tests** also passed for the version-reporting change.

At **23:46:18 UTC on 11 October**, the corrected standalone diagnostic was run
against the same unmodified signed 4.0.12 rehearsal service. Health, readiness,
individual administrator authentication, space accounting and MCP all passed:
three visible spaces, one accessible space, protocol `2025-06-18` and 12 compact
MCP tools. The API/worker/updater initialization receipts and clean shutdown were
verified. The live original service remained unchanged. This is a corrected
candidate client against a released server, not a claim that 4.0.13 was already
published or that the signed server package was patched in place.

## Setup and client compatibility

Authenticated `/v1/me` reports the serving package's `service_version`. The Python
response contract and TypeScript client permit its absence on earlier servers.
Both ordinary application and administrator identities receive the field on
the new service; it conveys no additional authority.

The built browser app was exercised at **1440 × 1000** and **390 × 844** using
an isolated loopback response fixture. Checks covered distinct app/server
versions, refresh to a changed server version, a legacy response without the
field, an unavailable server, and recovery after that failure. Failed/legacy
checks never display the app version as a substitute for the server version.
The connected session remained usable throughout.

Screenshots exposed missing page spacing in Setup; the screen now uses the same
responsive page container as the rest of Studio. The mobile layout has no page
horizontal overflow, including the longer older-server explanation. The update
guide link opens the bundled guide from Setup, and its internal managed-update
link opens the detailed guide with five code blocks and no page overflow at the
phone width. These browser response fixtures
verify presentation and compatibility states, not production service capacity
or native installation. Native release and public upgrade gates remain required.
