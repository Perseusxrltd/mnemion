# Changelog

## Unreleased

- Fixed ChromaDB legacy BLOB `seq_id` migration so it only converts `embeddings.seq_id`, never `max_seq_id.seq_id`.
- Added `mnemion repair --mode status|scan|prune|rebuild|max-seq-id`.
- Added HNSW bloat guard metadata for new collections and pure SQLite/HNSW divergence detection.
- Added MCP drawer management, explicit tunnel, reconnect, hook settings, checkpoint, and repair status tools.
- Added vector-disabled fallback behavior for MCP/Studio when HNSW divergence is detected.
- Added Gemini JSONL normalization, improved Claude Code tool context preservation, Slack speaker preservation, and a 500 MB normalizer guard.
- Added source adapter plugin scaffolding under `mnemion.sources`.
- Added first-run origin detection and `mnemion init --auto-mine` / `mnemion mine --redetect-origin`.
- Added Studio Anaktoron health fields and dashboard/status-bar health surfacing.
- Kept the coverage ratchet at 40% without excluding legacy modules; future ratchets should target 50% first, then 70%+ as legacy CLI/librarian/layer paths gain focused tests.
- Hardened repair follow-up behavior: rebuild now uses a verified temporary collection swap, prune keeps FTS/trust consistent after confirmed Chroma deletes, and `max-seq-id` repair is scoped to the configured drawer collection by default.
