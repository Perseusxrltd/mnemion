# Mnemion Mine

When the user invokes this skill, follow these steps:

## 1. Ask what to mine

Ask the user what they want to mine and where the source data is located.
Clarify:
- Is it a project directory (code, docs, notes)?
- Is it conversation exports (Claude, ChatGPT, Slack)?
- Do they want auto-classification (decisions, milestones, problems)?

## 2. Choose the mining mode

There are three mining modes:

### Project mining

    mnemion mine <dir> --consolidate

Mines code files, documentation, and notes from a project directory. The
`--consolidate` flag immediately extracts cognitive graph units for
reconstruction.

### Conversation mining

    mnemion mine <dir> --mode convos --consolidate

Mines conversation exports from Claude, ChatGPT, or Slack into the Anaktoron.

### Message-granular JSONL sweep

    mnemion sweep <jsonl-or-dir> --wing <name> --consolidate

Sweeps Claude/Codex JSONL transcripts message by message with deterministic
IDs and cursor resume.

Accepted rows can use top-level `role` + `content`, or a nested `message`
object with `role` and `content`. Content arrays are flattened, including
text blocks plus compact `tool_use` and `tool_result` summaries. Malformed JSON
and rows missing role/content are skipped and counted in the final summary.

### General extraction (auto-classify)

    mnemion mine <dir> --mode convos --extract general --consolidate

Auto-classifies mined content into decisions, milestones, and problems.

## 3. Optionally split mega-files first

If the source directory contains very large files, suggest splitting them
before mining:

    mnemion split <dir> [--dry-run]

Use --dry-run first to preview what will be split without making changes.

## 4. Optionally tag with a wing

If the user wants to organize mined content under a specific wing, add the
--wing flag:

    mnemion mine <dir> --wing <name>

## 5. Show progress and results

Run the selected mining command and display progress as it executes. After
completion, summarize the results including:
- Number of items mined
- Categories or classifications applied
- Any warnings or skipped files

## 6. Suggest next steps

After mining completes, suggest the user try:
- /mnemion:search -- search the newly mined content
- `mnemion reconstruct "question"` -- inspect evidence trails when provenance matters
- /mnemion:status -- check the current state of their Anaktoron
- Mine more data from additional sources
