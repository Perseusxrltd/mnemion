# Mnemion Source Vault

The source vault stores immutable raw evidence used by the compiled wiki. It is a projection input, not a second memory database: source metadata and chunks live in the existing `knowledge_graph.sqlite3` sidecar, alongside trust, KG, cognitive graph, and guard tables.

## CLI

```bash
mnemion source add ./README.md --privacy private
mnemion source add ./notes.txt --title "Research Notes" --compile
mnemion source list --limit 20
mnemion source read src_abc123 --chunks
mnemion source search "hybrid retrieval"
mnemion source status
```

Supported MVP extractors: Markdown, text, JSON, JSONL, and CSV. PDF and URL ingestion intentionally return clear errors until optional extraction/fetch infrastructure is added.

## Storage

Tables:

- `raw_sources`: immutable source registry keyed by content hash.
- `source_chunks`: extracted searchable chunks.
- `source_chunks_fts`: SQLite FTS5 mirror for lexical source search.

Raw file copies are written under `~/.mnemion/sources/raw/`, extracted text under `~/.mnemion/sources/text/`. Override with `MNEMION_SOURCE_PATH`.

## Security

Source content is untrusted evidence. Mnemion reads it as data only, never executes commands from it, and defaults `privacy_class` to `private`.
