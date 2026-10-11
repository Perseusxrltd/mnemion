# Evidence wiki, graph and curation

Version 4.0.10 adds the [live 3D memory map](memory-map.md),
with browser/desktop orbit, filters, original evidence, recorded activity and a
2D/list fallback. The wiki and earlier evidence graph below remain available.

Studio's **Wiki & graph** page organizes current accessible memories by subject,
shows source and entity relationships, and identifies exact duplicate text,
contested claims and unassigned subjects for review. Select a space or all
accessible spaces and optionally filter by subject. The graph supports mouse
and keyboard focus; Obsidian provides a full linked-vault visualization.

`POST /v1/knowledge` returns typed `memories`, `topics`, `nodes`, `edges`,
`findings`, Markdown, a revision fingerprint and generation time. It accepts
the same explicit-space/all-accessible selection as recall, a literal subject
filter, `limit` (1–1,000, default 250), and `include_historical` (default false).
Studio requests 250 memories and labels partial results. Graph overviews show
up to 12 nodes per kind; node selection focuses their direct connections.

Deleted and quarantined records are always excluded. Expired, future-valid,
retracted and superseded claims are excluded by default. Historical inclusion
retains their status. An organization administrator still needs content access.
Entity labels never reveal an inaccessible space. A final authorization and
version check rejects a view if access or an included memory changed during
rendering; refresh after `409 knowledge_changed`.

```python
view = client.knowledge(all_accessible=True, subject="Billing")
for topic in view.topics:
    print(topic.title, topic.memory_ids)
```

```ts
const view = await client.knowledge({ all_accessible: true, subject: 'Billing' })
```

MCP's `memory_map` returns the topic/relationship/review portion. Use
`memory_fetch` to inspect its references and `memory_context` for a token-bounded
context pack. Markdown HTTP links are relative to the workspace origin; for a
standalone linked vault, use the Obsidian export.

## Compilation, changes and source impact

Obsidian entity pages compile short, quoted evidence overviews with live review
status and memory/source links. Their frontmatter names the compiler and
`depends_on_revisions`. Revisions change those pages on the next refresh;
withdrawn or inaccessible memories are pruned from generated overviews. Personal
annotations are preserved by the same ownership manifests and conflict handling
as other notes. `vault --dry-run` provides the proposed refresh; edits in generated
regions produce explicit replacement files instead of being overwritten.

Studio's memory detail/history and incoming source proposals provide the current
revision comparison and review actions. A graph source/entity node identifies
its direct dependent memories. The original v3 `wiki` commands remain available
for private-profile compilation, diff jobs and linting; their old database is not
used as a shared-service authority.

The shared compiler uses recorded evidence and explicit entity metadata. It
does not infer that matching names identify the same person across spaces,
promote a repeated assertion to truth, or silently merge duplicate sources.
Optional LLM synthesis and legacy cognitive experiments remain separate from
these production read and lifecycle rules.
