# OpenClaw and Hermes conversation capture stores

**Source study and next implementation work, 2026-10-21.** Mnemion's JSONL
adapter does not read either provider's live database. Export compatibility is
not native provider capture or R07/C07 acceptance. Public 4.44.0 remains the
published baseline; the separate [retained-capture work](../service/durable-capture.md)
is unreleased. This study changes none of the 65 requirements or L1–L7 scope.

## Pinned sources

| Provider | Studied revision | Primary evidence |
| --- | --- | --- |
| OpenClaw | [`f960ba73bb163c6f83e41a6c195b5c7cb8e51301`](https://github.com/openclaw/openclaw/commit/f960ba73bb163c6f83e41a6c195b5c7cb8e51301) | Agent store/schema documentation, meeting transcript reference and event-byte design |
| Hermes | [`3f2afed3eb813cb00bd381d29b084d0e01de048f`](https://github.com/NousResearch/hermes-agent/commit/3f2afed3eb813cb00bd381d29b084d0e01de048f) | State store, canonical exporter and Gateway transcript implementation |

The private `openclaw-capture-upstream-sources.json` and
`hermes-capture-upstream-sources.json` manifests record immutable URLs, byte
lengths and SHA-256 hashes. All nine saved files match those records; the
originals remain unchanged. Their `original_tree_matches: false` values record
a tree/ref comparison, not a content-difference finding. Links below pin the
studied files rather than a moving branch.

The Hermes storage follow-up preserves additional pinned mixins and their URL,
size and SHA-256 manifests under the private evidence directory
`hermes-storage-contract-20261021-5fj9ehai/`. Its `sources*.json` files retain
the original fetch failures and successful retries separately. This was static
source/DDL inspection; no upstream code or provider journey was executed.

## OpenClaw: agent history is a tree in SQLite

The [agent store reference](https://github.com/openclaw/openclaw/blob/f960ba73bb163c6f83e41a6c195b5c7cb8e51301/docs/reference/session-management-compaction/store.md)
places mutable session rows and append-only transcript events together at
`~/.openclaw/agents/<agentId>/agent/openclaw-agent.sqlite` on the Gateway host.
Resolve the actual configured agent and host before selection. Files under
`agents/<agentId>/sessions/`, including `sessions.json` and legacy JSONL, are
migration/archive artifacts; current Gateway startup does not import them or
resume live JSONL reading.

The [session schema](https://github.com/openclaw/openclaw/blob/f960ba73bb163c6f83e41a6c195b5c7cb8e51301/docs/reference/session-management-compaction/schema.md)
distinguishes a routing `sessionKey` from its current transcript `sessionId`.
Events have `id` and `parentId`; their active path matters. An existing session's
`/new` or `/reset` appends a reset boundary in the same transcript, whereas
daily/idle rollover can create a new session ID. Rewrites append a replacement
suffix; message `supersedesEntryId` links to the immediately replaced entry and
can form a chain. Older rewrites and other event types may lack that link.
Archiving a session retains its history while removing it from active listings.
Neither active-list absence nor row `updatedAt` proves transcript deletion.
Stored aliases and database replacements also cannot be merged by spelling or
path: the upstream admission rules preserve exact physical identities.

Model context, displayed history and stored evidence are different projections.
Reset windows and compaction boundaries affect them differently. Full-fidelity
readers remain available for export/replay; the documented
`SessionManager.readSessionContext` exposes lazy entries within a read-only
snapshot callback. Laziness alone does not bound tree traversal or the size of
one decoded entry. The [event-byte design](https://github.com/openclaw/openclaw/blob/f960ba73bb163c6f83e41a6c195b5c7cb8e51301/docs/refactor/transcript-event-bytes.md)
also separates committed encoding from display/transport copies and requires
current authorization for each disclosure. Its remaining design work is not a
completed memory-budget guarantee.

The similarly named [`openclaw transcripts` reference](https://github.com/openclaw/openclaw/blob/f960ba73bb163c6f83e41a6c195b5c7cb8e51301/docs/cli/transcripts.md)
describes **meeting** transcripts in `$OPENCLAW_STATE_DIR/state/openclaw.sqlite`.
Its materialized `transcript.jsonl` files and browser utterance downloads are
meeting exports, with different projections and archive permissions. They do
not establish access to agent chat history.

## Hermes: live state and session exports differ

[`hermes_state.py`](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state.py)
owns the SQLite session database at `<Hermes home>/state.db`, with WAL support,
explicit read-only opens and database-generation checks. Session compression
can continue through parent/child sessions. The [Gateway transcript code](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/gateway/session_transcript.py)
follows durable compression successors, implements rewind through soft deletion
and supports rewrites that can remove stored rows. Its live replay reader can
repair message alternation; it is not an archival read contract. JSONL fallback
and retry spools serve recovery and must not be mistaken for the full live store.

The [canonical exporter](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_cli/session_export.py)
renders unfiltered JSONL as **one complete session object per line**, with a
`messages` array inside each object. It is not one message per line. Prompt-only
JSONL is a separate projection. `/save json` uses the session-object shape but
writes pretty-printed JSON, not JSONL.

Export selection is significant. The shared export helper includes compacted
rows for human transcripts and inactive rows with their flags for JSON snapshots.
`/save json` then removes undone rows: only active or compaction-archived messages
remain. Undo, compaction and deletion are not interchangeable. The exporter
materializes session data and applies its own export-message guard; it does not
provide Mnemion with a complete incremental event feed. The following contract
specifies the native adapter work still to implement against this pinned source.

### Schema and store identity

The declared [schema and triggers](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state_common.py)
use `SCHEMA_VERSION = 32`. That number is insufficient admission evidence:
the [schema mixin](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state_schema.py)
adds columns independently of versioned data migrations. It explicitly documents
converted JSONL stores whose `messages.id` remains `TEXT` without a primary key.
The adapter must inspect actual tables, columns, key types and required indexes
without running migrations. Unknown or incompatible shapes need a visible refusal.

| Stored object | Capture contract |
| --- | --- |
| `sessions` | `id TEXT PRIMARY KEY` identifies a physical session. Preserve `parent_session_id`, `source`, `created_source`, routing/profile fields, start/end reason and archive/hidden flags as selected provenance. `message_count` is not a complete-history count. |
| `messages` | Declared `id INTEGER PRIMARY KEY AUTOINCREMENT`, `session_id` reference and `(session_id, id)` index support insertion-order paging. Preserve role, typed content, tool/reasoning fields, timestamps and state flags according to the approved selection. Timestamps are not monotonic cursors. |
| Message identities | `message_uid` is logical identity carried through copies/imports; it is not unique, and bounded legacy backfill leaves some values absent. `platform_message_id` is optional. Keep physical row identity and payload revision separately; neither repeated text nor a shared UID authorizes discarding a row. |
| `system_prompts` | Hash-keyed prompt storage resolves `sessions.system_prompt_hash`; `tool_names` can also reference it. Resolve only selected references, with byte limits. A hash alone is not the original prompt. |
| `state_meta` | Key/value storage includes store identity, local lineage and retirement facts, but also runtime requests/results. Read only the bounded identity/lifecycle fields needed for selected sessions; never import the whole table. |
| Routing/runtime state | `gateway_routing` is keyed by `(scope, session_key)`. `conversation_generations` is keyed by `(source, session_key)` and survives history pruning. These routing generations, runtime revisions/epochs and admission sequences are not a transcript mutation journal. |

Fresh schema initialization records `store_instance_id` and
`store_created_at_utc`. The writer separately creates `db_file_generation` and
sets SQLite `application_id` from a 31-bit portion of that token. Read-only opens
do not create these facts. Older stores may lack them; a copied database retains
them. `application_id` is therefore neither a Hermes discriminator nor sufficient
store identity. Hermes also checks filesystem identity and WAL sidecars; a zero
on-disk application ID can mean an uncheckpointed WAL, not a replacement.

Bind a future capture cursor to the approved host/profile/path, verified physical
store incarnation and available generation facts. A path replacement, rollback,
copied store or missing identity evidence must invalidate automatic cursor reuse
and report the uncertainty. Do not mint provider identities or silently transfer
old capture/forgetting history to a replacement store.

### History state, rewrites and deletion

The [message mixin](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state_messages.py)
distinguishes stored rows from its model and display projections:

| State or operation | Meaning for capture |
| --- | --- |
| `active=1` | Current stored working set, which can include summaries and model-only rows; it is not automatically a visible user/assistant transcript. |
| `active=0, compacted=1` | Compaction-archived evidence. Display history can include it while model replay does not. |
| `active=0, compacted=0` | Removed from the live/display set. This includes undo/rewind and superseded carried copies; the flags alone do not prove a user requested forgetting. |
| In-place compaction | Archives covered rows and inserts new active rows atomically. Carried or concurrent tail copies can get new physical IDs while preserving logical IDs and payloads. |
| Replacement or pruning | `replace_messages` can delete rows, or preserve a common prefix and soft-archive the divergent suffix. `rewrite_pruned_rows` can archive an old twin and change the original row under the same ID. |
| Session archive/hidden state | Changes listing visibility while retaining messages. Default session lists also omit some children and superseded segments; they cannot certify deletion. |

The [prune/rewrite implementation](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state_prune_rewrite.py)
is a concrete counterexample to append-only capture: a row keeps its ID and
activity flag while its payload changes. Preserve observed revisions rather
than treating that ID as immutable content.

[Compression lineage](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state_compression.py)
requires a compression-ended parent and a genuine continuation. Exclude tool
children; branch, delegate and reset markers must match the actual parent. Copied
`model_config` markers alone are insufficient. Separately, the
[local owner receipt](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state_local.py)
under `gateway.local_policy.v1:<owner>` can bind multiple reset/compression
segments to one logical conversation. Preserve these relations and physical
session IDs; do not flatten every `parent_session_id` chain into one chat.
Missing, cyclic or over-budget ancestry remains a coverage gap.

Hermes does have [durable session retirement fences](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state_mutation_retirement.py):
`state_meta` keys `gateway.retired_session.v1.<id>` and separately namespaced
shared-route fences. Explicit-delete markers remain; eligible housekeeping
markers and terminal receipts can expire after the seven-day retry horizon.
Derived-session markers have additional permanence rules. These facts fence
session reuse, but contain neither every message deletion nor its prior content.
Observe them under the correct profile/namespace, without treating their absence
as proof that history never existed. The after-commit `on_session_delete` hook
also fires for deliberate archive and can fail; it is not a durable change feed.

### Export identity and evidence fidelity

There is **no reliable Hermes provider discriminator in the full-session export**.
The [portability mixin](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state_portability.py)
returns session fields plus `messages` and `timings`; lineage exports add
`segments` and `lineage_session_ids`. The renderer adds no fixed provider/format
header. `source` describes a surface or imported tool, and `billing_provider`
describes model billing. None of these fields or message roles proves Hermes
origin. Require an explicit trusted adapter choice; do not guess Hermes from a
generic `messages` array or inject a fabricated discriminator into producer data.

Exports are also decoded projections. `get_session` resolves shared prompts;
`get_messages` decodes sentinel-prefixed JSON content, tools and display metadata,
removes display-index fields and can drop unknown BLOB columns. Display reads
deduplicate copies and suppress model-only/removed rows. Use a specified,
type-preserving native record for selected column values and verbatim serialized
fields, with its own serialization version and digest. Label it as a native-row
snapshot, not original JSONL bytes or a recoverable SQLite backup. Apply approved
field selection before either evidence or readable text is persisted; omitted
fields must not survive in an auxiliary raw copy. If selection changes an encoded
field, retain only its selected encoding and identify the transformation. Field
selection does not scan ordinary string contents or perform automatic secret
detection.

Native selection must explicitly distinguish current messages, compaction
history and replaced/removed rows. The existing JSONL file presets do not imply
those provider-specific choices. Enrollment or migration must review that policy;
provider deletion is not automatically a Mnemion forget instruction.

### Read transaction and cursor contract

Use a dedicated, explicitly authorized read-only SQLite connection with a
correctly escaped [file URI](https://github.com/NousResearch/hermes-agent/blob/3f2afed3eb813cb00bd381d29b084d0e01de048f/hermes_state_holders.py).
Hermes uses `mode=ro`, `isolation_level=None` and bounded read waits/retries.
Its ordinary `_read_ctx` does not start a transaction, and `export_session`
fetches session metadata and messages separately. Consequently, a sequence of
export calls is not one consistent database snapshot. Display/ordinary object
methods may perform backfill or accounting work; do not use a writable
`SessionDB` as the collector.

The adapter must own an explicit read transaction for each claimed snapshot,
including its metadata, selected rows, lineage and lifecycle observations. Read
committed WAL state through SQLite; do not set `immutable=1` on a live store,
change journal mode, checkpoint, repair, create schema or copy only `state.db`.
WAL and rollback-journal operation both need bounded contention handling. Bound
transaction duration as well as rows, bytes, decode work and RAM, and close it
on cancellation. Failed reads never become empty inventories.

An **insert cursor is available**:
`get_messages(session_id, include_inactive=True, after_id=last_id, limit=N)`
pages physical rows by increasing ID. It refuses `after_id` with `latest`,
nonzero `offset`, `include_compacted` or `include_ancestors`. Limits on merged
lineage/display output can follow full input reads/deduplication, so those
methods are unsuitable as bounded evidence readers. The raw query shape to
implement, after verifying integer keys, is:

```sql
SELECT <approved columns> FROM messages
WHERE session_id = :session_id AND id > :after_id AND id <= :snapshot_high_id
ORDER BY id LIMIT :page_rows;
```

Take the upper ID in the same read transaction. Check selected-column byte
lengths before fetching/decoding payloads; a row limit does not bound one large
record. Commit accepted selected evidence and the append cursor together in
the encrypted inbox before attempting Mnemion delivery. Reopening a connection
starts a new observation, not a continuation of the old SQLite snapshot.

There is **no complete bounded mutation cursor in this storage contract**.
`conversation_revision()` combines active count, maximum ID, lineage and
`transcript_revision`; it is a live-view cache key. The revision trigger watches
selected payload columns, not every flag, UID, timestamp or display metadata
change, and is not a delete journal. Removing an archived row or updating a
reaction/UID can leave that fingerprint unchanged. Session/routing generations,
retirement keys and SQLite change counters do not supply the missing ordered
message revisions and tombstones. Data created and removed between polls may
be unrecoverable.

An append fast path therefore needs complete, bounded per-session reconciliation
for changed or removed older rows, plus an authoritative selected-session catalog
before declaring disappearance. Only a completed consistent snapshot may certify
that reconciliation; budget exhaustion or a restarted snapshot leaves coverage
incomplete and cannot authorize removal. Resumable reconciliation needs a reviewed
versioned snapshot mechanism. Lossless mutation capture, including changes between
polls, needs a provider-owned durable event/diff log; the studied storage interfaces
do not supply it. These remain implementation requirements, not guarantees to
infer from `after_id`.

### Hermes adapter acceptance cases to implement

- Admit the declared integer-key schema; refuse legacy text keys, missing required
  columns/indexes and unknown shapes without altering the provider database.
- Exercise committed WAL-only rows, live appends, in-place edits between pages,
  lock/IO failures, cancellation and database replacement/copies with unchanged
  generation tokens. Partial reads must retain visible coverage gaps.
- Verify compaction copies, repeated intentional text, missing/backfilled UIDs,
  changed content under a stable row ID, archived-twin pruning, undo and hard
  deletion. Keep physical evidence revisions separate from display deduplication.
- Distinguish genuine compression, forks and local reset-owner lineages; cover
  missing ancestors, hidden/archived sessions and session catalog limits.
- Cover permanent and expiring retirement markers, shared-profile namespaces and
  identifier reuse after housekeeping. Apply approved retention and current
  Mnemion revocation/forgetting decisions to queued replay.
- Check full-session JSONL, pretty JSON, lineage and prompt-only exports alongside
  unrelated lookalike exports. None may auto-enroll as authenticated Hermes data.
- Enforce record/page/transaction/RAM and inbox limits, including selected field
  exclusions, malformed encoded fields and BLOB values. Test crash/restart after
  local commit but before delivery under both app and headless ownership.

These are required tests and adapter boundaries, not executed acceptance cases.

## What Mnemion imports at this checkpoint

The [live adapter](../../mnemion/connectors/live_conversations.py) selects
`.jsonl` files, verifies complete record prefixes and tracks file generations,
byte/line ranges and digests. Its SQLite database is Mnemion's checkpoint,
not an OpenClaw or Hermes reader. File offsets do not describe native branches,
rewrites, compression lineage or provider deletion events.

The [normalizer](../../mnemion/conversations.py) can project a session object
containing `messages`, so a compatible Hermes export can produce readable notes.
This is generic shape matching, currently tagged `claude-export`; it does not
interpret Hermes `active`/`compacted` flags or preserve message IDs as capture
identities. Generic normalization must not be advertised as Hermes history
semantics. OpenClaw's event tree has no dedicated reader here. In `complete`
mode, selected valid JSONL can remain evidence even without a readable companion;
`messages` mode cannot manufacture a projection for an unsupported format.

A Hermes session-sized JSONL record must fit the live adapter's default 2 MB
record cap, configurable up to 16 MB. Fragment targets do not split a record.
Pretty-printed JSON belongs in the [complete-file export workflow](../service/capture.md),
within its separate bounds. Repeated exports are snapshots, not a provider
append protocol. Watching an arbitrary JSONL directory therefore cannot certify
complete live capture from either provider.

## Concrete next implementation work

1. **Establish provider contracts and enrollment.** Implement explicit selection
   of provider, host/profile, agent and sessions, with a bounded capability
   preview and reviewed content/retention policy. Implement the Hermes contract
   above and review OpenClaw's readers against the exact installed schema.
   Use authenticated provider reads or explicitly approved local
   access; database discovery and content never grant an audience or credentials.
   Keep meeting, agent, legacy-export and recovery-spool sources distinct.
2. **Read consistent, bounded history.** Build provider-aware snapshot/page
   readers with limits for bytes, records, tree traversal, decoded memory,
   elapsed work and cancellation. Account for WAL and database replacement;
   do not tail SQLite bytes, copy only a live main database or invoke repair
   paths as capture. OpenClaw's unbounded HTTP history default and Hermes'
   whole-session export allocation need explicit limits. Carry forward the existing
   [capture budgets](../service/live-conversations.md#bounded-work-and-remaining-limits)
   and [inbox limits](../service/durable-capture.md), with explicit provider units,
   visible refusal and resumable progress instead of silently skipped records.
3. **Preserve identity and history meaning.** Bind approved store incarnation,
   session and native event/message identities to payload digests and revisions.
   Record OpenClaw parent paths, reset windows and supersedence; distinguish
   Hermes compression continuations, inactive/compacted rows, rewinds and hard
   rewrites. Do not collapse branches or reused IDs into duplicate text. Missing
   links, replaced stores and history removed before observation remain explicit
   gaps, not reconstructed history or an empty successful read.
4. **Commit the approved evidence before delivery.** Preserve original exposed
   encodings where supplied, with stable IDs, hashes and native ranges/cursors.
   Label a serialization reconstructed from columns as such, never as original
   producer bytes. Apply approved field exclusions before persistence; message
   mode must not hide raw tool/reasoning data in provenance. Store the selected
   evidence and resume cursor atomically in the encrypted inbox before
   attempting delivery to Mnemion. Keep readable projections separate
   and replay exact delivery pages under current revocation/forgetting fences.
5. **Reconcile lifecycle and access explicitly.** Distinguish incomplete catalogs,
   archived/inactive sessions, provider deletion and a Mnemion forget decision.
   Retained selection survives producer removal only under its approved policy;
   absence alone cannot authorize erasure or renew access. Recheck provider
   authorization and mapped readers at each relevant read/delivery boundary.
   Cover both Studio and the independent headless lifecycle.
6. **Prove the actual providers.** Add fixtures and real provider journeys for
   forks, reset, rewrite chains, compaction, undo, concurrent writes, offline
   restart, WAL/store replacement, oversized records and revoked access. Verify
   exact selected evidence, stable identities, replay/deletion behavior and
   selected/omitted/unsupported counts. Report gaps and local acceptance,
   pending delivery, service acknowledgement and index readiness separately.
   Then run the applicable installed journeys on all six targets. No provider
   integration or packaged acceptance is established by this study; remaining
   L1 and full R07/C07 work stays open.
