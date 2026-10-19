# Independent-computer recovery and locale compatibility

Observed 19 October 2026, through 21:26 UTC. Candidate source: 4.27.0.
This report addresses the replacement-host acceptance in
[issue 38](https://github.com/Perseusxrltd/mnemion/issues/38).
Public release and installed-update acceptance are recorded separately in the
[release status](../RELEASE_STATUS.md).

## Defect reproduced

An authenticated fresh download from the operator's private Git recovery
repository supplied an encrypted host snapshot and a newer encrypted access
ledger. Every listed part and assembled file passed its SHA-256 check. The
decryption key came from an existing independent copy on the replacement PC.
Neither a database directory nor a runtime was copied from the live VPS.

The first attempt used the actual published 4.24 wheel, its signed service
manifest and frozen dependencies. The destination used the verified native
PostgreSQL 18.6/pgvector 0.8.7 runtime from the 4.24 build, a new private cluster,
new operator credentials and loopback listeners. The source used PostgreSQL 17.
No Mnemion database roles existed on the destination before restoration.

Restoration failed before publication. Both inventories had 69 tables and the
same row counts. Sixty-eight table hashes matched; only `memory_revisions`
differed, with 345 revisions in both copies. The source database used libc
`C.UTF-8`; the replacement cluster's default was `C`.

PostgreSQL does not dump stored generated-column values. It regenerates
`search_text` with `to_tsvector('simple', content)`, whose parsing depends on
`LC_CTYPE`. Repeating the same legacy archive on the same PostgreSQL 18 runtime
with the source locale passed **all 69 original full-row hashes**. This isolates
locale-dependent index generation; the PostgreSQL major-version change alone
was not the cause. No expected hash was edited or bypassed.

## Corrected behavior

New snapshots record their database locale and use inventory version 2. It hashes
all tables and all stored memory/revision/source/embedding values, excluding only
the generated keyword-index column after verifying its exact packaged definition.
PostgreSQL rebuilds that index for the destination. Legacy backups keep their
full-row checks and can use the explicit `--database-locale` option.

A new portable snapshot of the independently restored database then passed all
**71 table checks** into another database using the cluster's default `C` locale.
The two additional tables came from intervening compatible migrations. All 345
memory revisions matched under the portable inventory; their legacy full-row
hashes differed as expected. Embeddings matched, and every generated search value
equaled the destination's `to_tsvector` result. This second copy needed no locale
override or model call.

## Installed candidate and actual clients

A separately installed 4.27 candidate wheel performed the actual `host restore`
command using the original independently downloaded encrypted files. The command
verified all 69 backed-up tables, applied migrations, reconciled 141 deletion
records, retained seven eligible non-administrator application keys under the
explicit `preserve_applications` policy, and provisioned new API/worker logins.
It retained both organization identities. The historical owner key was refused;
the recovered owner received fresh credentials.

The restored Supervisor, API and worker became ready with cached public local
model weights. Actual HTTP and MCP calls demonstrated:

- The existing Codex and Grok keys still identified the original shared tenant
  without gaining administrator authority.
- Both clients fetched the two recorded original memories with their exact
  UTF-8 hashes and revision numbers. A previously deleted memory stayed absent.
- Both initialized MCP, discovered its 16 tools, fetched through `memory_fetch`
  and searched through the API.
- A new memory in a fresh private recovery-only space was indexed and found by
  hybrid search. The retained agent keys could not read that private space.
- After stopping and restarting the restored Supervisor, the new write and
  both original application credentials still worked.
- A native Windows Node process used Grok's existing protected credential file
  to connect to the restored service on the PC. MCP exact fetch and hybrid recall
  passed. No agent model turn or account login was required.
- The new memory was absent from the original VPS, and the original two memory
  hashes were unchanged there.

The restored API, worker, Supervisor and isolated PostgreSQL cluster were stopped
after the drill. No production cutover, Windows desktop profile change, new
hosting service, paid model call or additional subscription occurred.

## Regression coverage and limits

The focused recovery, application-key and host-loss suite covers real PostgreSQL
restores, complete hash checks, Unicode and embeddings across locales, corrupted
hashes, unknown inventory versions, legacy compatibility, generated-column
validation and immutable host-locale selection. Its host-loss fixture also
recreates an included filesystem source runner and survives a second database
loss. The first local suite invocation omitted the pinned `uv` tool from PATH;
the sole affected host fixture passed when rerun with that prerequisite present.
All **29 focused cases passed**, plus **four journal-ledger recovery cases**
covering original identities, later withdrawals and quarantines. The typed
desktop build, packaged web bundle, formatting and release-document checks also
passed. The source introduces no new dependency or schema migration.

The real VPS's Git runners are external OS services, rather than registered
Supervisor children. The real package therefore contained zero supervised source
runners; this drill does not claim to recreate those external services. Their
database identities and access state are covered by the verified snapshot.
Automatic external TLS, provider account, OS startup registration and cloud
provisioning remain separate operator steps.

The access ledger was captured at 20:45 UTC; it cannot represent later unknown
revocations or recover positive writes absent from the snapshot. This is the
current shared-agent tenant, **not** the lost original office database or vault.
That historical incident still requires its actual recovery inputs.

The 4.26 installed test passed on several targets but its Linux x64 run could not
find a recovery field. The 4.27 probe waits for controls to remain mounted through
rendered frames and identifies a missing selector. The complete installed
encrypted-backup, vault and restart checks remain mandatory; this local host drill
does not substitute for their cross-platform release results.
