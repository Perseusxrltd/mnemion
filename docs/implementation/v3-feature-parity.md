# V3 feature preservation audit

This audit compares the code at `c670e3039d2f7b43dbb00a2157e420e665203979`,
the preserved [v3 documentation](../legacy/v3-readme.md), and the implementation
in this branch. A historical README claim is not treated as proof of correctness.
“Legacy available” means the implementation remains in the optional private-profile
installation; it does not mean the workflow is available in the shared service.

| Useful previous behavior | Current disposition | Evidence / remaining work |
| --- | --- | --- |
| Local lexical + semantic retrieval | Adapted to scoped PostgreSQL + pgvector and pinned multilingual E5 | `service/retrieval.py`, real-model and retrieval integration tests; held-out release evaluation remains. |
| Wings, rooms, subjects, metadata | Original metadata and aliases preserved; shared spaces provide access boundaries | `service/legacy_import.py`, migration tests. A wing name never implicitly grants company access. |
| Trust, contradiction flags, quarantine, corrections | Separate observed/verified/contested states, reviewer gates, immutable revisions and private reasons | `service/memory.py`, `test_activity.py`, transaction/retrieval tests. Automatic LLM contradiction adjudication remains optional legacy work. |
| Raw source catalog and search | Source revisions, exact text spans, original migrated attachments; connector source updates | `service/memory.py`, `connector_*`, source/attachment HTTP tests. Binary ingestion is bounded and explicit. |
| Source hashes and provenance | Retained and strengthened | Pinned extractor/model identities, hashes, original IDs, Git commits, Slack author/thread/time, Drive file versions. |
| Conversation normalizers | Adapted to opt-in raw + readable shared capture | `conversations.py`, `docs/service/capture.md`, provider/client tests cover raw retention, Codex canonical events, active ChatGPT branches, Claude and Slack identities. Legacy `normalize.py` remains available. |
| Autosave hooks, diaries, session context | Shared watch and explicit session hooks; legacy writes remain durable and pause-aware | `capture/shared.py`, connector watch/leases, `ingestion.py`, MCP context. Hook input cannot choose a source or credential; incomplete scans do not prune. |
| Core working memory | Adapted to versioned, scoped core blocks and context packs | `service/memory.py`, `service/retrieval.py`, Studio Core Context. |
| Open Brain aliases | Available through the configured MCP compatibility space | `capture_thought`, `search_thoughts`, `list_thoughts`, `thought_stats`, `search`, `fetch` in `service/mcp.py`. |
| Drawer add/search/delete and historical IDs | Compatibility tools and scoped alias resolution retained | MCP/API/SDK tests; ambiguous old IDs require collection-qualified aliases. |
| Automatic agent configuration / snippets | Adapted to preview/apply CLI and Agents & apps Studio page | `agent_setup.py` preserves unrelated settings and backups; tests cover TOML policies/comments, JSON siblings, invalid configurations, and concurrent edits. No personal configuration was rewritten. |
| Obsidian owned mirror, annotations, paths, backlinks, graph | Retained and hardened across native clients | Shared refresh, portable filenames, stable-ID paths, manifests, manual sections, source anchors, conflict proposals. Native Obsidian and Windows/Linux desktop evidence exists; final native matrix remains. |
| Wiki compilation, diffs, lint and dependency inspection | Shared evidence wiki, live dependencies, review findings and owned refresh; original compiler retained | `service/knowledge.py`, compiled Obsidian entity overviews and `docs/service/knowledge.md`. Integration tests cover source changes, deletion during export, revocation during rendering and private entity exclusion. `wiki/` retains private-profile diff jobs. |
| Entity and cognitive graph reconstruction | Shared source/entity graph; optional legacy cognitive reconstruction retained | Studio Wiki & graph, MCP `memory_map`, native Obsidian links; legacy `cognitive_graph.py` and `knowledge_graph.py` remain optional. |
| Librarian / background tidy-up | Approved local/cloud models, bounded optional schedules, source-linked proposals, diffs, human review, guarded undo and durable budgets | Organization preserves source evidence and text. Findings never silently delete, merge or verify company facts. See the shared [librarian guide](../service/librarian.md). |
| Local / compatible LLM providers | Legacy available | `llm_backend.py`; core ingestion/retrieval does not require a remote LLM or send provider content to one. |
| LeWM, JEPA prediction, dialect compression | Retained as optional experiments | No production accuracy or cost claim without comparative evaluation. These are not permission or persistence foundations. |
| Complete export / restore | Expanded to verified full archives, migration, final delta and rollback | `service/recovery.py`, `legacy_archive.py`, `legacy_rollback.py`, real Chroma/PostgreSQL recovery tests. |
| Git-based union sync | Retired; historical implementation preserved | It could resurrect deleted data and ignore permissions. Git is now a source adapter; authoritative cross-device writes use the service. |
| Windows Studio installer and tray | Adapted to shared-service Studio; native platform packaging expanded | Sandboxed renderer/preload and local vault client. Final signing and all native targets are still release gates. |

Shared adaptation is recorded above; final native/release validation remains tracked in the implementation ledger. Experimental behavior stays optional and labeled. The final audit must
update this table with actual implementation and acceptance evidence before a
release-readiness claim.
