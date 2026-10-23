# Organization administration and workspace continuity

Updated **2026-10-23**. This contract extends requirements A01–A09 with the
explicit request that another authorized administrator must be able to manage
and recover a workspace when its original agent is unavailable. It is not a
claim that the controls below are already released.

The [4.8.0 directory batch](workspace-recovery-directory.md) implements shared
host/operator and recovery-material references, protected desktop observations,
an independent encrypted HTML viewer and equivalent agent operations. Its
[source acceptance](../validation/2026-10-15-recovery-directory.md) is separate
from native publication. The richer host health/delegation, recovery-custodian,
backup-delivery, identity-provider and safe-takeover requirements below remain open.

The [independent-PC recovery drill](../validation/2026-10-19-portable-host-recovery.md)
subsequently verified current encrypted Git delivery, existing application-key
continuity, exact memories and restart on another physical computer. Source
4.27 fixes its discovered locale mismatch. Source 4.28 adds private agent
selection of remote desktop accounts, with guarded identity and credential
handling. [Public HTTPS sign-in](../validation/2026-10-20-live-hosted-signin.md)
also passed scoped OAuth/MCP checks on the existing host, with new configuration
backed up off-host. The original office's unavailable full state, named-provider
acceptance, OS/provider provisioning and automatic failover remain separate.

## Independent host control checkpoint

The **22 October 2026 development source** adds a narrower independent-controller
milestone, described in the [user, administrator and agent guide](../guides/company-host-control.md).
The desktop `/hosts` route is available before memory sign-in, with protected
per-device Ed25519 logins and equivalent native-agent controls. An OS owner
adopts an existing managed Linux/macOS Supervisor host. Pinned restricted SSH
then enforces separate observer, operator and custodian roles without requiring
the memory API or the original agent. Memory membership never grants host
authority, and an ordinary browser cannot open this native connection.

Approved service operations retain durable intent and receipts across lost
replies. Reviewed signed upgrade plans require independent encrypted Git backup
readback before a new cutover; uncertain requests retain public recovery records.
The [local OS-owner recovery procedure](../guides/company-host-control.md#recover-custodian-authority-as-the-os-owner)
adds a fresh permanent custodian, optionally retires explicitly selected grants,
and preserves the host identity and server pin. It requires intact local
authority state. The memory-host backup does not escrow that independent
authority or operator keys.

[Focused source and fixture evidence](../guides/company-host-control.md#qualification-and-remaining-work)
covers profiles, archived requests/refused replay, actual local Node/Python/SSH
journeys with the memory API absent, owner recovery and backup retention. Builds,
lint/format and a bounded visual fixture also passed. The subsequent
[4.46.0 native qualification](../validation/2026-10-23-4460-native-acceptance.md)
passed all six installed targets, including OS-protected keys, transport refusal,
public recovery archives and offline `/hosts`. All six public installed-update
targets also passed. The [actual rollout](../validation/2026-10-23-4460-live-rollout.md)
updated Windows but rolled its shared host back to 4.45.1; production adoption
and both custodians' operational acceptance remain pending. Current published
packages and gates remain owned by [release status](../RELEASE_STATUS.md).

The **23 October source follow-up** adds [durable service policy](../guides/company-host-control.md#preserve-approved-stops-in-os-supervision):
adoption preserves the observed stopped/running state, and approved effects save
intent independently of receipt retention or later revocation. The OS owner
must replace unconditional memory startup and watchdog repair with the foreground
manager and locked `memory-repair` path, separately register the controller and
retain the official supervision stop action. Generated startup files are not
installed. Format-2 authority state refuses experimental format 1 without reset.
The [new policy checks](../validation/2026-10-22-independent-host-control.md#durable-service-policy--23-october-2026)
and frontend build passed; the validation preserves two fixture setup errors
and their targeted passing rerun. These source results do not qualify production
job/watchdog integration, which remains pending.

This advances delegation while the independent controller and computer are
reachable. It does not supply whole-machine provider wake, registered boot/login
startup, universal host adoption, an independently hosted browser controller,
replacement-host provisioning or safe failover. Production adoption/recovery, independent authority
custody, full Git-backup retrieval/restore and fencing an old writer remain open.
The broader acceptance contract below is retained.

## Ownership must survive the original agent

A workspace belongs to its organization or individual owner. The agent that
installed it is one identifiable application with delegated access. Running out
of model tokens must not stop an independently supervised memory service or
remove a person's ability to administer it.

The app must distinguish membership, memory access and hosting authority. A
member's computer is not necessarily a replica or a recovery host. Joining must
show what is on this device, where the service runs and who can recover it.

| Authority | Intended controls | Content access |
| --- | --- | --- |
| Organization owner | Ownership, administrator policy, recovery custodians and host adoption | Explicit space grants; ownership does not silently grant all private memories |
| Organization administrator | People, applications, invitations, sessions, devices and assigned organization settings | Explicit space grants |
| Host operator | Approved start/stop/restart, network health, updates, backup/restore and host migration | Separate host credential; a memory key is insufficient |
| Space administrator / reviewer | Compartment membership and review, retention and deletion within assigned scope | Assigned spaces only |
| Contributor / reader | Save or retrieve memories permitted by their grants | Assigned spaces only |

An owner may hold several roles. Every delegated operation must recheck its
current authority and leave an audit event. Require explicit adoption before a
host accepts remote operations, and expose typed actions rather than arbitrary
shell execution. Define protection against losing the final recovery custodian
or active administrator, including concurrent revocations and expired keys.
Document that a database/OS operator can access the host's underlying data;
application space grants are not protection against that operator.

## An offline recovery view in the app and on an independent entry point

Keep a protected, bounded recovery record on each enrolled admin device, and
optionally on organization-controlled hosting separate from the memory server.
It must remain usable when the server, its original agent or its tunnel is down.
Show:

- Stable workspace identity and the last verified membership and authority,
  clearly dated and marked as cached while offline.
- Registered primary/recovery hosts, their roles and last observed health; the
  actual failure layer (device, service, tunnel, authentication or permissions).
- Independently accessible operator controls or the configured hosting console,
  without embedding keys in URLs or granting host access to ordinary members.
- Backup and deletion/access-ledger locations, verification time, restore-test
  results, known recovery age and missing data. A source mirror is labeled as such.
- Actions to test a connection, reconnect to a verified replacement endpoint,
  inspect recovery material and perform an explicitly authorized recovery.

An offline role snapshot explains the last known access; it cannot authorize a
new write or override later revocation. Cache no plaintext credentials or memory
content in a public portal. Protect credential destinations, validate replacement
host identity and require explicit selection before forwarding credentials.
Keep recovery material outside the single host whose loss it must survive.

## Recovery from Git or another storage provider

Git, Drive, object storage and company-managed providers can hold source material,
verified backups, or both. Identify the contents before offering recovery:

| Material | What can be recovered | What must not be assumed |
| --- | --- | --- |
| Git/Markdown source mirror | Tracked files and available revisions, then a new search index with source provenance | Unexported memory writes, organization identities, grants, sessions, deletion ledger or the original database |
| Verified Mnemion database backup and current recovery ledger | The state covered by the backup and ledger, subject to the existing restore contract | Writes after the backup or absent ledger events |
| Enrolled and synchronized recovery replica | The acknowledged state and documented lag under the replication protocol | Zero data loss, current authority or safe takeover without fencing the old writer |

An [operator exercise on 12 October](../validation/2026-10-12-encrypted-workspace-backup.md)
verified an encrypted database/ledger copy outside the original host, independent
Windows decryption, and restoration with migrations into a separate database.
This evidence covers a concrete snapshot; it does not close the app workflow,
scheduling or independent host inventory requirements.

Use the [existing recovery procedure](../service/recovery.md) for complete
backups. Preserve the original host/database and recover into a separate target.
Review revoked access and deleted content before admitting clients. Report
source-only restoration as a recovery copy until a deliberate reconciliation
has been completed; never claim that it is the same live workspace merely
because its display name matches.

For later automatic failover, specify leader ownership, fencing, replication
acknowledgements, recovery point/time objectives and conflict handling first.
Two writable copies must not silently diverge. A stable URL alone cannot make a
stopped computer available; independent hosting or a recovery replica supplies
that continuity. These features must work on free, user/company-owned hosting
without making a paid central service mandatory.

## Acceptance

1. Enroll an owner, a second human administrator, an independently authorized
   operator and a restricted agent, then join a second device. Verify each role
   through the app and its equivalent API/CLI/MCP or local operator interface.
2. Remove the original agent's key and stop its session. Other authorized users
   still administer the running workspace and the service remains supervised.
3. Stop the primary host and its tunnel. The second admin device still displays
   its recovery view without revealing another tenant's data or treating cached
   permissions as current authorization.
4. Restore a verified backup and ledger on another supported host, test revoked
   access and deleted memories, and reconnect the verified workspace. Repeat
   with only a source mirror and prove that the UI reports the partial scope.
5. Restart the old host. It cannot become a second writer through stale routing,
   remembered membership or old credentials. Exercise concurrent admin changes,
   key expiry and failed/interrupted recovery.
6. Record real Windows/macOS/Linux and browser evidence, including a live
   unattended update while a workspace is remembered. Exercise safe bounded
   load against an authorized test space; do not alter shared production memory
   for convenience or equate an offline preparation with a completed stress test.

Published 4.0.11 adds explicit administrator creation in the app/SDK, an
organization roster and administration pages that do not require a memory-space
grant. Real API and browser checks retain a second administrator after disabling
the original identity, without implicit content access. Named retirement in the
app and final-current-admin protection across concurrent API/OAuth changes are
also validated; these cannot verify possession of another key or future renewal.
Protected desktop connections now include a dated, encrypted identity/role
observation and an offline **Details & recovery** view. Inspection makes no
network request and never turns cached access into authorization; older or
locked records have explicit states. Local host controls, diagnostics and
verified database recovery are also foundations. Sign-in/invitations, pending
unverified connection profiles, registered hosts and backup locations, an
independent recovery entry point, operator delegation, guided restoration and
complete agent parity remain required implementation.

The [actual Windows recovery and isolated lab](../validation/2026-10-12-workspace-administration.md)
subsequently verified provider operator wake without an agent session, separate
human administration, native 4.0.12 join/reopen, an explicit Git reader mapping
and bounded synthetic write/index/search/revision/delete checks. The original
remote service was then [migrated from 4.0.0 to managed 4.0.12](../validation/2026-10-12-managed-workspace-upgrade.md)
with a fresh encrypted off-host backup, preserved access and repeated Windows
checks. The original host then completed a [signed automatic 4.0.12 → 4.0.13
patch](../validation/2026-10-12-v413-release.md), including an independently
verified pre-patch backup and unchanged membership, keys and space roles.
The actual Windows desktop also installed and relaunched 4.0.13 after the normal
ten-minute inactivity interval. Its saved human administrator reconnected
without the original agent or re-entering a key; startup and background settings
were preserved.

A later suspended-host observation exposed a [Linux clock/readiness
problem](../validation/2026-10-12-host-clock-readiness.md). Published 4.0.14 corrects
process-birth checks and RAM sampling across a clock change; it does not wake
a suspended provider or update an older operator executable. The original host
then passed an [operator-applied 4.0.13 → 4.0.14 patch and Windows administrator
reconnection](../validation/2026-10-12-v414-release.md), with preserved keys,
grants and its public address. The existing host-management channel remains
necessary for provider suspension. These live results
advance the contract; they do not complete independent hosting, replicas,
the recovery entry point, operator delegation or failover.

Source 4.4.0 adds [app-managed remote access](../service/remote-access.md) for a
locally hosted workspace: an owned ngrok session or existing HTTPS proxy,
supervised route checks, hosted web/consent pages, public invitation links and
equivalent private operator commands. A real local proxy outage left local
authorization available and recovered after reconnection. This advances
independence from an agent session while the computer is running; it does not
create host inventory, power management, a replica, operator delegation or an
independent recovery portal. Ordinary memory administrator authority still
cannot reconfigure another computer.
