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
cases passed on Linux and both native Macs in the [complete product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38255848416)
at `4465755e7119366baa58d5512e18ae58d80a9ba4`. Python 3.12/3.13/3.14,
both containers, the web build, legacy tests and dependency audits also passed.

The production Studio bundle contains 321 files / 2,755,078 bytes, with 125
licensed components in its notices. A real browser at **13:43:57 UTC** displayed
the connector guide at 1440 px and 390 px without page overflow or JavaScript
errors. Guide search, selection, the internal service-guide link and 4.1.3 notes
worked while all external and workspace requests were blocked. Both screenshots
were visually reviewed. This [browser record](2026-10-12-v413-docs.json) checks
the built local assets without a running workspace backend; native installer
and public update tests are recorded separately below.

## Published release

The [complete release workflow](https://github.com/Perseusxrltd/mnemion/actions/runs/38255904034)
passed all **30 jobs**, including native databases, installed local workspace
creation/search/reopen, and installer/update/relaunch gates on Windows, macOS
and Linux for x64 and ARM64. Windows ARM retains its documented x64 backend.
All artifacts use the same source commit recorded above.

The [automatically triggered hosted verifier](https://github.com/Perseusxrltd/mnemion/actions/runs/38260497593)
passed at **14:07:56 UTC** while the release remained a draft. Its
[receipt](2026-10-12-v413-hosted-verification.json) records all **38 assets /
3,865,169,704 bytes**, production signatures, complete feeds and unchanged
uploaded IDs, sizes and digests. The checksum inventory's SHA-256 is
`748a57ae4df2b6af5451fbe6aaf592b4c0f6bcacd75e0d27ff1d36e1dbb44073`.

[Version 4.1.3](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.1.3)
was published at **14:10:17 UTC**. The [14:10:55 public verification](2026-10-12-v413-publication.json)
confirmed the exact source tag, latest stable release, unchanged asset inventory
and all 12 anonymous metadata/checksum/update feeds. The automatic
[website synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/38260961479)
completed. The [six public 4.1.2 → 4.1.3 upgrade rehearsals](https://github.com/Perseusxrltd/mnemion/actions/runs/38260961324)
completed successfully at **14:21:38 UTC**. Their [sanitized receipts](2026-10-12-v413-public-upgrades.json) confirm unchanged public packages, official feeds, real system idle, process replacement and preserved profiles on all six targets. This is separate from the prepublication native gates and actual-user deployment.

At **14:13:32 UTC**, [anonymous live HTML checks](2026-10-12-v413-website.json)
confirmed the product page's visible 4.1.3 label, all six installer links,
current notes/guides/checksums, the roadmap on `main`, and the homepage link to
the product page. This checks the new release metadata on the unchanged website;
no new visual render is claimed.

This is host-managed lifecycle support. It does not silently adopt an existing
unmanaged process, deploy to another computer, add Windows/Compose fleet control,
provide company sign-in or configure an OS startup entry. The actual shared
host's old runner still needs its one-time controlled adoption. Its successful
automatic API/worker patch was independently confirmed by the original reporter,
so [issue 11](https://github.com/Perseusxrltd/mnemion/issues/11) is closed. The
separate connector issue 22 remains open until that adoption is verified.
