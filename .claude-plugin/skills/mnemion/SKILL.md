---
name: mnemion
description: Mnemion — mine projects and conversations into a searchable memory palace. Use when asked about mnemion, memory palace, mining memories, searching memories, or palace setup.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Mnemion

A searchable memory palace for AI — mine projects and conversations, then search them semantically.

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

Run the appropriate instructions command, then follow the returned instructions step by step.
