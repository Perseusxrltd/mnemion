# Migrating v3 memory and preserving rollback

Migration uses a complete [legacy archive](recovery.md), an explicitly selected
organization and owner, and a private space that stays paused until final cutover.
It does not infer team access from a wing, an author name, or a directory.
Use database administration credentials for these offline commands.

## Rehearsal and initial import

Stop v3 MCP, Studio, hooks, capture, miners, sweeper, Obsidian edits, and old Git
sync tasks before taking an archive. The updated entry points also honor a
persistent pause. Older binaries and direct SQLite/Chroma writers do not honor
that marker, so stopping them remains necessary.

```bash
mnemion-service legacy-freeze --profile /path/to/legacy-profile
mnemion-service legacy-backup --profile /path/to/legacy-profile \
  --writers-stopped --output /backups/legacy-initial.mnemion
mnemion-service import-v3 /backups/legacy-initial.mnemion \
  --tenant TENANT_UUID --owner OWNER_UUID --report /backups/import-initial.json
```

The report identifies the new space, canonical counts, archive checksum, and
exceptions. Repeating the same import while the destination remains in migration
does not create extra revisions. Later snapshots update changed records; an older
snapshot cannot replace a newer one. A v4 change made outside the paused writer
boundary becomes a visible conflict instead of being overwritten.

The importer preserves original IDs as scoped aliases, original timestamps in
evidence, trust history, conflict/correction references, original metadata, core
blocks, and original source bytes. Raw files up to 64 MiB per attachment enter the
source evidence API. Larger or missing files are reported, and their records stay
quarantined. The complete archive retains every captured file. Original metadata
too large for the API is retained in `legacy-evidence.json`. Unsupported memory
content is explicitly reported and retained in the archive.

V3 `current` becomes an observed claim; it does not become independently verified
because of a confidence score or verification counter. Contested and superseded
claims retain those states. Missing or unknown trust is quarantined. Raw sources
without vector chunks become source notes. Durable pending writes are imported
from their journal payloads. Current deletion records take precedence over both
stored rows and pending writes.

Graph, cognitive, and compiled-wiki tables remain preserved in the original
archive and are counted in the report. They are not imported as verified facts.
The normal v4 worker rebuilds embeddings from canonical text using its pinned
pipeline; v3 vectors are not mixed into the new generation.

## Reconcile the copied Obsidian vault

Use a copy of the original vault and the reported space ID:

```bash
mnemion-service --credentials owner.mnemion-credentials.json \
  vault --path /path/to/copied-vault --spaces IMPORTED_SPACE_UUID --review
```

The existing manifest and imported aliases retain managed note paths. Personal
annotations, unmanaged notes, and `.obsidian` settings remain intact. Older notes
without reliable generated hashes produce conflict proposals at their existing
paths; inspect those proposals before accepting them. Open the copied vault in
Obsidian and check links, source blocks, graph navigation, and representative
annotations. Keep review and ordinary exports in separate vaults.

Resolve an original ID through `GET /v1/spaces/{space_id}/resolve?legacy_id=...`,
Python `client.resolve_alias(...)`, or TypeScript `client.resolveAlias(...)`.
The MCP compatibility fetch/delete tools resolve aliases inside their configured
space. If an ID occurs in several collections, the report identifies ambiguity;
the unambiguous alias is `collection-id:original-id`.

## Final delta and cutover

If v3 was resumed after rehearsal, stop every writer again and create a fresh
persistent pause. Keep this **final archive**: rollback requires its exact backup
ID, not the initial rehearsal snapshot.

```bash
mnemion-service legacy-freeze --profile /path/to/legacy-profile
mnemion-service legacy-backup --profile /path/to/legacy-profile \
  --writers-stopped --output /backups/legacy-final.mnemion
mnemion-service import-v3 /backups/legacy-final.mnemion \
  --tenant TENANT_UUID --owner OWNER_UUID --final \
  --report /backups/import-final.json
```

If exceptions remain, the command exits with status 2 and the space stays paused.
Resolve them, or document the disposition of every exception and repeat with
`--accept-exceptions SHA256_FROM_REPORT` and a new report filename. That hash
acknowledges exactly the reviewed exception set. Missing rows without deletion
records are exceptions; absence alone cannot silently erase memory.

`cutover_complete: true` means the final transaction recorded its archive/watermark
and opened the new space. Check worker readiness, representative retrieval and
source evidence, then switch client configuration to the service. Grant each app
the required space role. Keep v3 paused, and retire the old sync/capture jobs.
Routing changes remain explicit; the importer does not edit other applications.

## Roll back after v4 has accepted writes

Export the v4 tail before changing routing. This command waits for in-flight
application writes and persists a pause, then captures live memories, all their
revisions/sources/attachments, core-block history, aliases, and current deletions:

```bash
mnemion-service rollback-export --tenant TENANT_UUID --space IMPORTED_SPACE_UUID \
  --output /backups/v4-tail.mnemion
```

Replay using the Python 3.12 installation with the locked `legacy` extra and the
legacy profile's own embedding model:

```bash
mnemion-service rollback-restore --legacy /backups/legacy-final.mnemion \
  --tail /backups/v4-tail.mnemion --path /recovery/verified-legacy-copy
```

The command verifies both archives before creating a new destination. It applies
current deletions, replays and verifies canonical content hashes, and preserves
quarantine and core blocks. It re-embeds with the legacy pipeline; equal vector
dimensions do not make E5 and MiniLM compatible. Missing dependencies/models or
an interrupted replay fail without publishing the destination.

Rollback also rebuilds the raw-source catalog and lexical chunks from current
memory, invalidates generated wiki/graph views, and refreshes the copied Obsidian
vault. Old managed source text cannot remain searchable after a correction or
withdrawal. Original evidence remains in the verified recovery archives.
Edited wiki pages, personal notes, annotations, and Obsidian settings are preserved.
Conflicts are reported in `projections`; `ready_to_resume: false` requires review
before reopening the recovered profile. A source with any quarantined or disputed
chunk stays quarantined because v3 cannot express independent chunk permissions.

The result remains paused and includes its exact `freeze_id`. V3 is a private
profile: it does not acquire v4 team authentication or native immutable revision
history. The full tail is retained under `recovery/`, and original attachments
under `sources/v4-rollback/`, so those richer records remain recoverable. Validate
retrieval and inspect the refreshed Obsidian view before redirecting clients and
running `legacy-resume --profile ... --freeze-id ...`. Never resume both writer
systems against diverging copies.

To abandon rollback and continue using v4, resume the service space using the
exact pause token reported by `rollback-export`:

```bash
mnemion-service resume-space --tenant TENANT_UUID --space IMPORTED_SPACE_UUID \
  --token PAUSE_TOKEN
```

Failure to write a rollback archive leaves v4 paused so retry is safe. An Obsidian
ZIP is a visualization export; it cannot substitute for either recovery archive.
