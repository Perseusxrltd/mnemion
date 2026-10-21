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
provide Mnemion with a bounded incremental event feed. Native schema and
portability behavior delegated to the imported Hermes mixins still need direct
review before choosing a database reader or cursor.

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
   preview and reviewed content/retention policy. Verify the pinned upstream
   reader implementations and schema versions, including Hermes' delegated
   modules. Use authenticated provider reads or explicitly approved local
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
