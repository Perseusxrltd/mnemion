# Wiki + Open Brain Compatibility Implementation Status

## Summary

Implemented an additive source vault, compiled wiki MVP, context packs, Obsidian export, clean-room Open Brain-compatible MCP aliases, native source/wiki MCP tools, minimal capture CLI path, and Studio backend endpoints. Mnemion remains canonical; the wiki is a derived Markdown projection.

## Completed

- Source vault tables, extraction, chunking, FTS5 search, idempotent content-hash ingestion.
- Deterministic compiled wiki pages with YAML frontmatter, generated-section markers, source pages, index/log, skeletal concept/entity pages, claim comments, and claim rows.
- Wiki review/dry-run jobs with diff artifacts and apply flow.
- Wiki linter for frontmatter, marker balance, claim provenance, and citation coverage.
- Context packs combining wiki pages, source chunks, and current drawer hits when available.
- Managed compiled-wiki Obsidian export under `_Mnemion/Compiled Wiki/`.
- Open Brain-compatible MCP aliases over native Mnemion systems.
- Native MCP source/wiki tools.
- Minimal `mnemion capture "text"` and `mnemion capture watch <folder>` paths.
- Studio backend endpoints for sources, wiki status/pages/compile/lint/jobs/context packs.
- Alpha hardening integration harness for mixed source ingestion, capture, review/apply, lint, context packs, and Obsidian export using isolated temp paths.
- Trust/privacy hardening for stale source hashes, quarantined evidence, contested warnings, sensitive/quarantined Obsidian export skips, and MCP fetch refusals.
- MCP registry-path round-trip coverage for `search` and `fetch` over drawer/source/chunk/wiki IDs.
- Review-job apply now updates `wiki_pages` and `wiki_claims`, so `wiki status` and downstream tools see pages applied from review jobs.

## Pending

- Full LLM-assisted synthesis pages beyond deterministic MVP.
- Rich contradiction surfacing beyond stored trust/citation metadata.
- Source Chroma indexing is available as an opt-in hook but not defaulted on for tests or CLI.
- PDF, URL, OCR, webhook capture, HTTP MCP transport, and Studio frontend source/wiki views.
- Broader KG fact hydration in context packs.

## Changed files

- `mnemion/sources/*`
- `mnemion/wiki/*`
- `mnemion/mcp/compat/openbrain.py`
- `mnemion/capture/*`
- `mnemion/config.py`
- `mnemion/cli.py`
- `mnemion/mcp_server.py`
- `studio/backend/main.py`
- `docs/source_vault.md`
- `docs/wiki_compiler.md`
- `docs/openbrain_compat.md`
- `docs/wiki_agent_schema.md`
- `docs/implementation/wiki_openbrain_status.md`
- `README.md`
- `SYSTEM_PROMPT.md`
- `.codex-plugin/README.md`
- `.claude-plugin/README.md`
- `studio/README.md`
- `tests/test_sources_store.py`
- `tests/test_sources_ingest.py`
- `tests/test_source_search.py`
- `tests/test_wiki_renderer.py`
- `tests/test_wiki_compiler.py`
- `tests/test_wiki_linter.py`
- `tests/test_wiki_context_pack.py`
- `tests/test_mcp_openbrain_compat.py`
- `tests/test_wiki_obsidian_export.py`
- `tests/test_wiki_openbrain_alpha_hardening.py`
- `tests/test_studio_backend.py`

## New CLI commands

- `mnemion source add|list|read|search|status`
- `mnemion wiki compile|lint|query|context-pack|blast-radius|diff|apply|open|status|export-obsidian`
- `mnemion capture "text"`
- `mnemion capture watch <folder>`

## New MCP tools

- `capture_thought`
- `search_thoughts`
- `list_thoughts`
- `thought_stats`
- `search`
- `fetch`
- `mnemion_source_add`
- `mnemion_source_list`
- `mnemion_source_read`
- `mnemion_source_search`
- `mnemion_wiki_compile`
- `mnemion_wiki_page_get`
- `mnemion_wiki_lint`
- `mnemion_wiki_context_pack`
- `mnemion_wiki_blast_radius`
- `mnemion_wiki_export_obsidian`

## New storage tables

- `raw_sources`
- `source_chunks`
- `source_chunks_fts`
- `wiki_pages`
- `wiki_claims`
- `wiki_links`
- `wiki_jobs`

## Tests added

- Source store, ingest, and FTS search tests.
- Wiki renderer, compiler, linter, context-pack, and Obsidian export tests.
- MCP Open Brain compatibility tests.
- Studio backend source/wiki endpoint tests.
- Alpha hardening integration tests for mixed sources, duplicate ingestion, review/apply, stale-source linting, quarantined filtering, sensitive/quarantined export skips, and MCP typed-ID round trips.

## Commands run

```bash
uv run pytest tests/test_sources_store.py tests/test_sources_ingest.py tests/test_source_search.py -q
uv run pytest tests/test_wiki_openbrain_alpha_hardening.py -q
uv run pytest tests/test_mcp_openbrain_compat.py::test_registry_search_fetch_round_trip_for_source_chunk_wiki_and_quarantine -q
uv run pytest tests/test_wiki_compiler.py tests/test_wiki_linter.py tests/test_wiki_context_pack.py tests/test_wiki_obsidian_export.py tests/test_wiki_openbrain_alpha_hardening.py -q
uv run pytest tests/test_mcp_openbrain_compat.py tests/test_studio_backend.py -q
uv run pytest tests/test_wiki_renderer.py tests/test_wiki_compiler.py tests/test_wiki_linter.py tests/test_wiki_context_pack.py -q
uv run pytest tests/test_source_search.py tests/test_mcp_openbrain_compat.py -q
uv run pytest tests/test_wiki_obsidian_export.py tests/test_studio_backend.py -q
uv run pytest tests/test_sources_store.py tests/test_sources_ingest.py tests/test_source_search.py tests/test_wiki_renderer.py tests/test_wiki_compiler.py tests/test_wiki_linter.py tests/test_wiki_context_pack.py tests/test_mcp_openbrain_compat.py -q
uv run pytest tests/test_sources_store.py tests/test_sources_ingest.py tests/test_source_search.py tests/test_wiki_renderer.py tests/test_wiki_compiler.py tests/test_wiki_linter.py tests/test_wiki_context_pack.py tests/test_wiki_obsidian_export.py tests/test_mcp_openbrain_compat.py tests/test_studio_backend.py -q
uv run python -m mnemion --help
uv run python -m mnemion source add C:\tmp\mnemion-wiki-openbrain-smoke\note.md --compile
uv run python -m mnemion wiki lint --json
uv run python -m mnemion wiki context-pack "hybrid retrieval" --token-budget 1000
uv run python -m mnemion capture "Open Brain compatibility captures normal Mnemion drawers." --tag compat
uvx ruff format mnemion\cli.py mnemion\mcp_server.py mnemion\wiki\claims.py mnemion\wiki\compiler.py mnemion\wiki\context_pack.py mnemion\wiki\linter.py mnemion\wiki\obsidian_export.py mnemion\wiki\renderer.py mnemion\wiki\store.py tests\test_mcp_openbrain_compat.py tests\test_sources_store.py
uvx ruff format tests\test_mcp_openbrain_compat.py tests\test_wiki_openbrain_alpha_hardening.py
uvx ruff format mnemion\wiki\compiler.py
uvx ruff check .
uvx ruff format --check .
uv run pytest -q
git diff --check
```

## Passing checks

- Combined targeted source/wiki/MCP/Studio suite: 37 passed.
- Alpha hardening suite: 4 passed.
- Focused post-hardening source suite: 9 passed.
- Focused post-hardening wiki suite: 14 passed.
- Focused post-hardening MCP/Studio suite: 17 passed.
- CLI smoke: source add with compile, wiki lint, context-pack, capture, and `--help` passed against isolated temp paths.
- Ruff lint: passed.
- Ruff format check: passed.
- Full pytest: 266 passed, 1 skipped, 106 deselected.
- Git whitespace check: passed.

## Failing/skipped checks

- Initial `uv run pytest` attempts in the sandbox failed because `uv` could not access its cache. The same commands passed when run with approved escalation.
- Studio frontend build/audit not run because this implementation only changed the Studio backend and no frontend files.

## Privacy/security notes

- Source privacy defaults to `private`.
- Source content is treated as untrusted data.
- Compiled wiki is generated output and not canonical storage.
- Obsidian export skips pages marked `privacy_class: sensitive` unless explicitly included and always skips quarantined pages by default.
- Context packs and Open Brain-compatible `fetch` exclude or refuse quarantined evidence by default and surface contested warnings.
- Studio mutating endpoints remain covered by the existing `MNEMION_STUDIO_TOKEN` middleware.

## Manual usage examples

```bash
mnemion source add ./README.md --privacy private --compile
mnemion wiki compile --all --review
mnemion wiki diff wjob_abc123
mnemion wiki apply wjob_abc123
mnemion wiki lint
mnemion wiki context-pack "hybrid retrieval" --mode technical_deep_dive
mnemion wiki export-obsidian
mnemion capture "Remember that source-backed claims are required." --tag mnemion
```

## Next steps

1. Expand deterministic synthesis/timeline/review pages and deeper contradiction surfacing.
2. Enable richer source Chroma indexing by default once embedding startup cost is acceptable in local/test environments.
3. Run Studio frontend build/audit if frontend files are changed in a later phase.
4. Add HTTP MCP gateway only after stdio tooling has baked.
