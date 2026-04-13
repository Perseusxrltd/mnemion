# Mnemion — System Prompt Template

Copy-paste this into any AI system that has access to the Mnemion MCP server.
This tells the AI *when*, *where*, *how*, and *why* to use its memory.

---

## Universal system prompt (paste into any AI)

```
You have access to a persistent memory Anaktoron via the Mnemion MCP tools (mnemion_*).
This is your long-term memory — it persists across all sessions and conversations.

MANDATORY PROTOCOL:

1. ON STARTUP: Call mnemion_status immediately. It returns your full behavioral protocol,
   the AAAK memory format spec, and an overview of all stored memories. Do not skip this.

2. BEFORE ANSWERING any question about a person, project, past event, or fact:
   Call mnemion_search or mnemion_kg_query first.
   Never guess about something that might be in the Anaktoron — verify.

3. WHEN YOU LEARN SOMETHING NEW (new project, new fact, user corrects you, something changes):
   Call mnemion_add_drawer to save it. New relationships go to mnemion_kg_add.

4. WHEN A FACT CHANGES:
   Call mnemion_kg_invalidate on the old fact, mnemion_kg_add for the new one.

5. AT END OF EVERY SESSION:
   Call mnemion_diary_write with your name and a summary of what happened,
   what you learned, what matters. This is your journal across time.

KEY RULE: Storage alone is not memory. Storage + this protocol = memory.
The Anaktoron is only useful if you read it before speaking and write to it after learning.
```

---

## Platform-specific setup

### Claude Code (`~/.claude/CLAUDE.md`)
Copy the system prompt above into `~/.claude/CLAUDE.md` (global) or into a `CLAUDE.md`
in the project directory. Claude Code reads this file at every session start.

### Cursor (`.cursorrules` or `.cursor/rules`)
Add the system prompt to your `.cursorrules` file in the project root, or add it
as a global rule in Cursor Settings → Rules for AI.

### Claude.ai Projects (claude.ai)
In a Project, paste the system prompt into "Project Instructions".
Any conversation in that project will inherit it automatically.

### ChatGPT (Custom Instructions)
Go to Settings → Personalization → Custom Instructions.
Paste the system prompt into "What would you like ChatGPT to know about you?" or
"How would you like ChatGPT to respond?".

### Gemini (system_instruction in API)
Pass the system prompt as `system_instruction` when initializing a chat session.
For Gemini Advanced, paste it into the conversation at the start of each session.

### Any OpenAI-compatible API
Pass as the `system` message in the messages array before any user turns.

---

## Why this works

The Mnemion MCP server exposes tools that any AI can call. But tools alone don't create
behavior — the AI needs to *know* to call them. This system prompt is the behavioral layer
that tells the AI:

- **When**: startup, before answering, when learning, at end of session
- **Which tool**: status first, search before answering, add_drawer when learning, diary at end
- **Why**: because storage without retrieval is not memory

The server also exposes a `mnemion_protocol` MCP prompt (via `prompts/get`) for clients
that support MCP prompt injection — those clients receive the protocol automatically.
