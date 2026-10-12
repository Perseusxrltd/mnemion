# Original workspace migration and managed service adoption

Recorded on **2026-10-12** against the original shared workspace and its actual
Windows administrator client. The remote service moved from **4.0.0 to 4.0.12**
at **00:06:56 UTC**. This was an explicit operator migration, not a desktop
update or an automatic schema-changing patch.

## Backup and preparation

The [earlier encrypted backup](2026-10-12-encrypted-workspace-backup.md) had
already been independently decrypted on Windows and restored into a separate
database. That copy passed migration, restricted database-role checks, managed
API/worker/updater readiness, authenticated API/MCP checks and clean shutdown.

Immediately before the live migration, the old runtime captured another
consistent database snapshot at **00:06:27 UTC** and a newer deletion/access
ledger at **00:06:37 UTC**. The complete archive was verified, encrypted to the
same two independent age recipients, decrypted for a host-side hash check and
published to a new branch in the existing private recovery repository. The two
ciphertext files total **49,742,454 bytes**. The source-memory branch was unchanged.

After the switch, Windows fetched the remote copy, matched the manifest to the
operator-observed digest, verified both ciphertexts and independently decrypted
them through bounded streams with its DPAPI-protected recovery identity. Both
plaintext sizes and hashes matched. Neither a plaintext backup nor its identity
was written to Windows. Peak verification-process memory was **36,978,688 bytes**.
The fresh snapshot was not restored a second time; the preceding snapshot's
isolated restoration and the fresh copy's integrity/decryption checks are
separate evidence.

## Live transition

The staged 4.0.12 runtime was verified against its publisher-signed manifest,
immutable package inventories and migration checksums. The operator plan
verified the existing startup scripts and the birth identities, ownership and
working directories of six Mnemion process groups before draining them. The
existing tunnel remained running.

Migrations `012_connector_sync_requests.sql` and `013_oauth_bindings.sql` were
applied transactionally to the original database. Identity, API-key and space-
grant inventories matched before and after migration and service initialization.
No database restore, replacement organization or new public address was used.

The new managed supervisor runs the API, worker and update watcher. Restricted
API/worker database logins remain separate from the updater's private owner
credential. None of the supervised children inherits the owner database URL.
Readiness checked the actual process identities and private initialization
receipts. The original startup entry now invokes the managed service and its
existing proxy/source/tunnel sidecars; a second invocation preserved the running
processes without duplication. This verifies idempotent startup, not a full
provider-machine reboot.

The original HTTPS destination and all existing keys/grants were preserved.
The proxy now routes both API and MCP to the unified service, and the existing
Git source runner uses the verified 4.0.12 installation with its existing
configuration. Automatic managed service updates are enabled with the default
six-hour interval and jitter. A later automatic version transition remains a
separate observation; enabling a watcher does not prove that transition.

## Actual Windows checks after migration

Fresh authenticated checks passed for the separate human administrator:
the same organization, three spaces, two administrator space grants, one Git
reader grant, six visible principals, six keys and the existing connector.
Scoped lexical recall returned Git evidence. The installed app opened its
**People & apps** and **Connections** administration pages under that human
identity. No original-agent conversation or model session was needed.

The human then used **Connections → Sync now** in the installed app. The durable
request advanced from generation 0 to 1, and the upgraded source runner completed
generation 1 successfully. It checked **386 unchanged Git items**, with zero
changes/removals, in **4.030 seconds**; the client observed completion after
**8.766 seconds**. This was a real app request and source scan, with no agent
model session and no direct operator invocation of the scan.

The original agent's unchanged key separately passed health, identity, readiness,
space and MCP checks, retaining its contributor and reader scopes and no
organization-administrator authority. MCP initialization listed 12 compact tools.

The isolated Windows lab then repeated save/idempotency, background indexing,
lexical/semantic recall, revision/stale-write rejection and deletion. All three
synthetic memories were cleaned up. **40 requests** completed in **21.259 seconds**,
with p50 **219.75 ms**, p95 **244.66 ms** and maximum **1,388.18 ms**. Peak client
RSS was **44,650,496 bytes** and minimum free Windows RAM was **1,514,483,712 bytes**.
No production memory writes or cloud-model calls occurred. These bounded client
timings are not a capacity benchmark. The
[lab's explicit limits and scope checks](2026-10-12-workspace-administration.md)
remain enforced.

## Remaining work

This proves recovery and administration of this original deployment without its
agent session. Host wake still uses the provider's authenticated computer
controls. Scheduled off-host backups, registered recovery locations, delegated
host operations, guided restoration and safe failover remain on the
[continuity plan](../implementation/workspace-continuity.md). The source runner
and tunnel have separate upgrade lifecycles; the managed API/worker updater does
not imply fleet-wide updates of every surrounding program. Windows/fleet/Compose
policy and automatic migration-bearing service upgrades also remain incomplete.
