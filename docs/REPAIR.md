# Mnemion Repair Guide

Mnemion keeps the ChromaDB vector store, SQLite FTS mirror, trust records, and knowledge graph local-first. Repair commands are designed to inspect first, back up by default, and avoid loading unsafe vector segments when possible.

## Health Status

```bash
mnemion repair --mode status
```

This reads `chroma.sqlite3` and HNSW `index_metadata.pickle` directly. It does not open a Chroma client. Run this first. If SQLite contains far more embeddings than HNSW metadata, MCP and Studio disable vector loading and fall back to lexical status/search behavior.

## max_seq_id Poisoning

Dry-run first:

```bash
mnemion repair --mode max-seq-id --dry-run
```

Repair with confirmation:

```bash
mnemion repair --mode max-seq-id --yes
```

Optional flags:

```bash
mnemion repair --mode max-seq-id --segment <segment-id> --yes
mnemion repair --mode max-seq-id --all-collections --yes
mnemion repair --mode max-seq-id --from-sidecar /path/to/clean/chroma.sqlite3 --yes
mnemion repair --mode max-seq-id --no-backup --yes
```

By default, max-seq-id repair is scoped to the configured Mnemion drawer collection. Use `--all-collections` only when you have intentionally put multiple Chroma collections in the same Anaktoron and want to repair all poisoned rows. Backups are created by default as `chroma.sqlite3.max-seq-id-backup-<timestamp>`.

## HNSW Rebuild

Use this when status reports a diverged HNSW index:

```bash
mnemion repair --mode rebuild
```

The rebuild extracts all drawers, compares the extracted count against SQLite ground truth, backs up `chroma.sqlite3`, builds a temporary collection with Mnemion HNSW guard metadata, verifies the temporary count and metadata, then swaps the temporary collection into place. The previous collection is kept under a temporary backup name during the swap so rollback can restore it if final verification fails.

If extraction appears capped or shorter than SQLite, rebuild aborts. Only override after independent verification:

```bash
mnemion repair --mode rebuild --confirm-truncation-ok
```

## Scan And Prune

```bash
mnemion repair --mode scan
mnemion repair --mode prune --yes
```

`scan` writes corrupt IDs to `corrupt_ids.txt`. `prune` deletes only those IDs and requires `--yes`.

After Chroma confirms an ID was deleted, `prune` removes that drawer from the FTS mirror and marks its trust record `historical` with reason `repair-pruned`. If Chroma deletion fails for an ID, FTS and trust are left untouched for that ID. Knowledge graph triples are retained because older triples do not reliably encode drawer-source ownership; invalidate KG facts explicitly if a pruned drawer was their only source.
