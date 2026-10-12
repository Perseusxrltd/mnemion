# Independent administration and the connected Windows lab

Recorded on **2026-10-12 Europe/Paris** (2026-10-11 UTC) using the actual Windows
installation and its original remote workspace. The initial exercise used
desktop **4.0.12** with shared service **4.0.0**. The original service was
[subsequently migrated and adopted as a managed 4.0.12 host](2026-10-12-managed-workspace-upgrade.md)
at 00:06:56 UTC on 12 October. Updating a desktop does not migrate its
organization server.

## Recovery without the original agent

The provider's existing authenticated computer controls woke the original host
without a conversation or model request to the unavailable agent. The host's
owner credential was recovered through that authorized operator channel using
an authenticated encrypted transfer, then used to enroll a separate human
administrator and individual key. No owner credential was printed or placed in
public evidence.

The new human key authenticated independently, listed the organization roster
without a memory-space grant, and received an explicit administrator grant to
the ordinary writable office space. The original agents remained enabled with
their original restricted keys. Production agent revocation was not used as a
test; separate [API/browser acceptance](2026-10-11-independent-administration.md)
covers that case in an isolated environment.

The Windows app joined through its normal form with the new key, saved the
connection using operating-system protection, and showed the human organization
administrator and administration controls. A normal quit/reopen at 22:49 UTC
reauthenticated the same workspace without entering the credential again.
Automatic update, background and login-startup preferences remained enabled.
The [release report](2026-10-11-v412-release.md) distinguishes the actual manual
Check/Restart update from unattended public upgrade acceptance.

## Git source access

The Git source retained its source-managed permission boundary. Its explicit
published-member configuration gained one human mapping with the **reader**
role; existing agent bindings were preserved. The previous private connector
configuration was backed up before replacement. A fresh provider access
observation reconciled the new mapping, without a document import, memory
mutation or model call. The new human key then successfully read a memory in
the Git compartment.

An initial permission-only diagnostic failed before changing configuration or
bindings: its 512 MiB virtual-address cap prevented the Go Git credential helper
from starting. A controlled check reproduced that reservation failure and
confirmed that the provider check succeeds without that inappropriate virtual
limit. This was a diagnostic constraint, not a lost Git permission or a product
authorization bypass.

## Isolated Windows validation

A dedicated synthetic-test space and a separate application identity were
created through the human administrator. In this initial cycle its device key
had **reviewer access only to the test space**, no organization-administrator authority and a
90-day expiry. Fresh checks proved that it cannot list organization principals
or access either existing production compartment. The key is protected by
current-user Windows DPAPI. Only the human administrator and that application
hold test-space grants.

The test space uses the already approved **E5 small local CPU model** on the
remote host, with no network model egress. The Windows client starts no local
model or memory service. Before work, the harness verifies the exact tenant,
principal, sole permitted space and active model generation, and refuses an
unexpected candidate model.

The bounded cycle passed on the actual Windows PC:

| Check | Observed result |
| --- | --- |
| Save and duplicate request | Three synthetic memories; replay returned the original memory and operation receipt |
| Background indexing | All three operations reached ready |
| Lexical and semantic recall | Each query returned its expected synthetic evidence within the explicit test scope |
| Revision | New content/version persisted; a stale-version write returned a conflict |
| Cleanup | All three synthetic memories were deleted and became unavailable |
| Production content / paid model calls | No production memory writes; no cloud model calls |

The run made **39 requests in 19.65 seconds**, with p50 **216.35 ms**, p95
**252.67 ms** and maximum **367.97 ms**. Peak client RSS was **44,617,728 bytes**;
the minimum observed free system RAM was **630,173,696 bytes**. These are
client-observed timings on this connection, not a server capacity benchmark or
a representative retrieval-quality evaluation.

Enforced limits are one in-flight request, two requests per second, 120 total
requests, 120 seconds for work plus 45 seconds for scoped cleanup, 128 KiB per
response and 192 MiB client RSS. Work refuses less than 512 MiB free system RAM.
A private run record tracks synthetic IDs and pending cleanup; a native file
lock prevents overlapping runs. Fixture checks verified rejection of a wrong
tenant, wrong space, changed model, foreign-memory cleanup and an exhausted
request budget before live work.

The earlier [40-search read-only baseline](2026-10-11-workspace-gateway.md)
remains a separate observation. Reports contain numerical results and private
test identifiers, never credentials, private destinations or production memory
contents.

## Remaining continuity work

Following the original host's controlled 4.1.0 migration and automatic 4.1.1
patch, the same lab identity was **reduced to contributor**. A new actual
Windows cycle passed at **10:38:33 UTC** with 41 requests, including guarded
read-only policy checks through the separate human administrator. All memory
operations used contributor authority, all three synthetic memories were
withdrawn, and cleanup completed. The
[4.1.1 acceptance record](2026-10-12-model-idle-release.md) preserves the result
and the two corrected private-harness assumptions without changing the
historical reviewer measurements above.

The individual human administrator and connected test client remove dependence
on an agent session for normal use. Host wake still uses the provider's operator
controls. A saved client connection or Git Markdown copy is not a complete
replica, current recovery ledger or independently available server.

The [full encrypted backup and isolated restore/migration](2026-10-12-encrypted-workspace-backup.md)
passed independently. The [live managed-host migration](2026-10-12-managed-workspace-upgrade.md)
also passed fresh human/agent authentication, preserved Git access and another
complete isolated Windows lab cycle. Scheduled independent backups, registered
recovery locations, delegated host operators and guided recovery remain required. Continue
[the continuity contract](../implementation/workspace-continuity.md) and
requirements A06, A11–A13, U06 and U11 without claiming automatic failover or
the full roadmap complete.
