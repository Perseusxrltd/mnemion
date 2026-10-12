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
cases run on Linux and both native Macs in CI; their results and the release's
native/public delivery gates remain to be collected.

This is host-managed lifecycle support. It does not silently adopt an existing
unmanaged process, deploy to another computer, add Windows/Compose fleet control,
provide company sign-in or configure an OS startup entry. The actual shared
host's old runner still needs its one-time controlled adoption after publication.
