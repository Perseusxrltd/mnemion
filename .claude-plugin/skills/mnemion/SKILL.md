---
name: mnemion
description: Mnemion — mine projects and conversations into a searchable memory Anaktoron. Use when asked about mnemion, memory Anaktoron, mining memories, searching memories, or Anaktoron setup.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Mnemion

A searchable memory Anaktoron for AI — mine projects and conversations, then search them semantically.

## Prerequisites

Ensure `mnemion` is installed:

```bash
mnemion --version
```

If not installed:

```bash
pip install mnemion
```

## Usage

Mnemion provides dynamic instructions via the CLI. To get instructions for any operation:

```bash
mnemion instructions <command>
```

Where `<command>` is one of: `help`, `init`, `mine`, `search`, `status`.

For newer operational paths that do not have slash-command wrappers yet, call
the CLI directly:

```bash
mnemion sweep <jsonl-or-dir>
mnemion consolidate --limit 1000
mnemion reconstruct "query" --json
mnemion memory-guard scan
mnemion memory-guard review --out ./memory_guard_review
mnemion repair --mode status
mnemion eval moat --suite all
```

Run the appropriate instructions command, then follow the returned instructions step by step.
