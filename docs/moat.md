# Mnemion Moat

Mnemion's edge is not a bigger vector database. The moat is the combination of memory lifecycle, structured reconstruction, and operational guardrails around the corpus.

## What Mnemion Adds

| Layer | Purpose | User-facing commands |
|-------|---------|----------------------|
| Hybrid RRF retrieval | Exact lexical recall plus semantic search, fused without replacing either signal. | `mnemion search` |
| Trust lifecycle | Current, superseded, contested, historical, and quarantined states with audit history. | `mnemion verify`, `mnemion challenge`, `mnemion memory-guard scan` |
| Contradiction detection | New memories can demote older conflicting drawers instead of letting both compete forever. | Background on save, Librarian pass |
| Cognitive graph | Raw drawers become typed units: propositions, causes, prescriptions, preferences, objectives, and events. | `mnemion consolidate` |
| Topic tunnels | Repeated concepts across current drawers become graph paths that can expand reconstruction beyond exact query overlap. | `mnemion reconstruct` |
| Active reconstruction | Searches evidence units first, then hydrates raw drawers with an evidence trail. | `mnemion reconstruct --json` |
| Memory guard | Detects obvious instruction-injection and privacy-exfiltration memories, writes report-only review artifacts, and can quarantine on explicit request. | `mnemion memory-guard scan`, `mnemion memory-guard review` |
| Moat eval | Built-in deterministic cases for structure, causality, forgetting, and security. | `mnemion eval moat --suite all` |

## Recommended Workflow

1. Ingest data:

   ```bash
   mnemion mine ~/projects/myapp --consolidate
   mnemion sweep ~/logs/codex --wing codex --consolidate
   ```

2. Refresh cognitive units when large batches are already in the Anaktoron:

   ```bash
   mnemion consolidate --limit 1000
   ```

3. Search for answers through reconstruction when provenance matters:

   ```bash
   mnemion reconstruct "what did we decide about retrieval scoring?"
   mnemion reconstruct "what did we decide about retrieval scoring?" --json
   ```

4. Review risky memories before deciding whether to quarantine:

   ```bash
   mnemion memory-guard scan
   mnemion memory-guard review --out ./memory_guard_review
   # Optional, explicit write path:
   mnemion memory-guard scan --quarantine
   ```

5. Run moat eval before release branches or storage changes:

   ```bash
   mnemion eval moat --suite all
   python benchmarks/moat_benchmark.py --suite all
   ```

## Response Shapes

`mnemion reconstruct --json` returns:

```json
{
  "query": "retrieval",
  "results": [
    {
      "id": "drawer_1",
      "text": "...",
      "wing": "project",
      "room": "memory",
      "source": "notes.md",
      "evidence_trail": [
        {
          "unit_id": "cog_...",
          "unit_type": "proposition",
          "text": "Retrieval scoring includes trust status.",
          "matched_cues": ["retrieval"],
          "via_topic_tunnel": "retrieval"
        }
      ]
    }
  ],
  "topic_tunnels": [
    {
      "cue": "retrieval",
      "drawer_count": 2,
      "unit_count": 2,
      "drawer_ids": ["drawer_1", "drawer_2"],
      "units": ["..."]
    }
  ]
}
```

`mnemion eval moat --suite all` returns a stable schema:

```json
{
  "suite": "all",
  "kg_path": null,
  "modes": ["raw_vector", "hybrid_rrf", "trust_kg", "cognitive_reconstruction"],
  "scores": {},
  "case_counts": {},
  "cases": {}
}
```

Each case has a `name` and a `passed` object with one boolean for every mode.
The CLI uses an isolated temporary SQLite DB for built-in eval fixtures so it does not write synthetic records into the live knowledge graph.

`benchmarks/moat_benchmark.py` wraps the same deterministic cases with benchmark metadata and per-mode totals. Treat it as a locally reproducible Mnemion-moat proof, not as a raw vector-recall leaderboard.

`mnemion memory-guard review --out <dir>` reads existing `memory_guard_findings`
from the knowledge graph and writes `memory_guard_review.md` plus
`memory_guard_review.csv`. It does not rescan drawers, change trust state, or
quarantine anything. The CSV columns are `drawer_id`, `risk_type`, `score`,
`reason`, `wing`, `room`, `source`, `created_at`, and `redacted_snippet`.

## Configuration

| Key | Environment | Default | Meaning |
|-----|-------------|---------|---------|
| `backend` | `MNEMION_BACKEND` | `chroma` | Storage backend entry point. |
| `embedding_device` | `MNEMION_EMBEDDING_DEVICE` | `auto` | Embedding provider target: `auto`, `cpu`, `cuda`, `dml`, or `coreml`. |
| `entity_languages` | `MNEMION_ENTITY_LANGUAGES` | `en` | Entity pattern locales, comma-separated. |
| `topic_tunnel_min_count` | `MNEMION_TOPIC_TUNNEL_MIN_COUNT` | `2` | Minimum drawer support before a repeated cue becomes a topic tunnel. |

## Current Boundary

The cognitive extractor is intentionally lightweight. It gives Mnemion a testable structured layer now, but it is not yet a full semantic parser. The next research-grade upgrades should improve extraction quality, add larger eval datasets, and expose evidence trails in Studio.
