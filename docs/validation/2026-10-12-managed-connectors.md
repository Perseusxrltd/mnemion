# Managed connector lifecycle — 2026-10-12

[Issue 22](https://github.com/Perseusxrltd/mnemion/issues/22) reports the original
shared host's separately launched connector still using 4.0.12 after its managed
API/worker automatically reached 4.1.1. Version 4.1.3 adds an explicit
[managed launch mode](../service/managed-connectors.md), retaining the existing
connector configuration and scope identity.

The focused connector, update, cleanup, transport and supervision checks passed
**88 tests**. This includes a real temporary PostgreSQL service and real scanner
processes, source ingestion before/after service restart, unchanged source memory
IDs, verified-backup creation and restricted service credentials. One local test
initially stopped because the pinned `uv` executable was not on its test PATH;
it passed after supplying the existing pinned executable explicitly. No product
behavior was weakened to bypass that prerequisite.

Process tests exercise successive 4.1.2/4.1.3/restored-4.1.2 scanner fixtures,
private absolute configuration snapshots, retained token/SSH references,
database/owner environment filtering, simultaneous shared scan leases, blocked
runtime replacement, a child retaining its lease after launcher exit, duplicate
launcher rejection, graceful stop and provider subprocess cleanup. Rejected
configuration data stays out of diagnostics. Status distinguishes current
process birth identities from stale/reused PIDs.

The updater's short retry and live, expiring wait marker are checked separately
from network traffic. The marker pauses new scans while existing scans drain;
abandoned process identity or expiry cannot indefinitely pause ingestion.
Handoff tests check explicit verified protocol support, released scan locks,
preserved original paths and filtered credentials.

The real signed/locked installation tests have also been extended to ingest
source documents before and after installation, preserve source IDs, execute
the real launcher handoff, stop cleanly, and process a source deletion after a
failed candidate restores the previous runtime. These two opt-in installation
cases passed on Linux and both native Macs in the [complete product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38255848416) at `4465755e7119366baa58d5512e18ae58d80a9ba4`. Python 3.12/3.13/3.14, both containers, the web build, legacy tests and dependency audits also passed. The separate release native/public delivery gates remain to be collected.

The production Studio bundle contains 321 files / 2,755,078 bytes, with 125
licensed components in its notices. A real browser at **13:43:57 UTC** displayed
the connector guide at 1440 px and 390 px without page overflow or JavaScript
errors. Guide search, selection, the internal service-guide link and 4.1.3 notes
worked while all external and workspace requests were blocked. Both screenshots
were visually reviewed. This [browser record](2026-10-12-v413-docs.json) checks
the built local assets without a running workspace backend; native installer
and public update tests remain separate.

This is host-managed lifecycle support. It does not silently adopt an existing
unmanaged process, deploy to another computer, add Windows/Compose fleet control,
provide company sign-in or configure an OS startup entry. The actual shared
host's old runner still needs its one-time controlled adoption after publication.
