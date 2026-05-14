# Mnemion Compiled Wiki

The compiled wiki turns Mnemion sources, drawers, and evidence into Obsidian-friendly Markdown. Mnemion remains canonical; the wiki is a derived artifact.

## CLI

```bash
mnemion wiki compile --all --review
mnemion wiki diff wjob_abc123
mnemion wiki apply wjob_abc123
mnemion wiki compile --source src_abc123 --apply
mnemion wiki lint
mnemion wiki context-pack "hybrid retrieval" --mode technical_deep_dive
mnemion wiki export-obsidian
```

`compile --all` defaults to review mode unless `--apply` is explicit. Generated sections are marked with `MNEMION:BEGIN` and `MNEMION:END`; manual sections outside those markers are preserved on recompilation.

## Generated Pages

The deterministic MVP writes:

- `index.md`
- `log.md`
- `sources/<source-slug>-<source_id>.md`
- skeletal `concepts/<term>.md`
- skeletal `entities/<entity>.md`

Source pages include claim provenance comments such as:

```html
<!-- claim:claim_abc123 source:src_456 chunk:sch_456_0000 confidence:0.9 -->
```

Source page paths include the source ID so two files with the same title or stem
cannot overwrite each other. Older `sources/<source-slug>.md` pages may remain as
manual/unmanaged files until a manifest-managed cleanup is run.

Generated source evidence is rendered as quoted, untrusted evidence. Source text
is never treated as agent instruction; instruction-like phrases such as "ignore
previous instructions", "exfiltrate", "send secrets", or "system prompt" produce
a `source_instruction_text_visible` lint warning.

## Live Provenance

Compiled frontmatter is not authoritative for trust/privacy after review. Lint,
context packs, MCP wiki fetch, and Obsidian export resolve live provenance from
`raw_sources` and `wiki_claims` in SQLite. If DB state disagrees with generated
frontmatter, the DB wins:

- changed source hashes emit `stale_source_hash`;
- changed source trust emits `stale_source_trust_status`;
- quarantined sources block context/wiki fetch/export by default;
- contested sources remain visible in private context flows with explicit warnings;
- sensitive sources are denied from Obsidian export unless explicitly included.

## Linting

`mnemion wiki lint` checks frontmatter, generated marker balance, source-page claim comments, stale source hashes, stale source trust, low citation coverage, contested/superseded visibility, quarantined evidence, sensitive export risk, and instruction-like source evidence. It does not auto-resolve contested or sensitive evidence.

## Context Packs

Context packs retrieve relevant compiled pages and source chunks, then optionally hydrate current drawers through hybrid search. Quarantined evidence is excluded by default; contested evidence is included with explicit warnings. This is the preferred agent path for large topics.

## Live Rollout Gate

Before pointing the compiler/exporter at a live vault:

1. Run the copied-vault stress harness or a fresh temp-path equivalent.
2. Confirm `mnemion wiki lint` has no quarantined evidence errors.
3. Confirm `mnemion wiki export-obsidian` skips quarantined and sensitive pages by default.
4. Confirm MCP `search` to `fetch` round-trips still refuse quarantined `source:`, `chunk:`, and `wiki:` IDs.
5. Only then opt into live source/wiki paths.
