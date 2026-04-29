#!/usr/bin/env python3
"""
normalize.py — Convert any chat export format to Mnemion transcript format.

Supported:
    - Plain text with > markers (pass through)
    - Claude.ai JSON export
    - ChatGPT conversations.json
    - Claude Code JSONL
    - OpenAI Codex CLI JSONL
    - Slack JSON export
    - Plain text (pass through for paragraph chunking)

No API key. No internet. Everything local.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024


def normalize(filepath: str) -> str:
    """
    Load a file and normalize to transcript format if it's a chat export.
    Plain text files pass through unchanged.
    """
    try:
        if os.path.getsize(filepath) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"{filepath} is too large to normalize safely (>500 MB)")
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        raise IOError(f"Could not read {filepath}: {e}")

    if not content.strip():
        return content

    # Already has > markers — pass through
    lines = content.split("\n")
    if sum(1 for line in lines if line.strip().startswith(">")) >= 3:
        return content

    # Try JSON normalization
    ext = Path(filepath).suffix.lower()
    if ext in (".json", ".jsonl") or content.strip()[:1] in ("{", "["):
        normalized = _try_normalize_json(content)
        if normalized:
            return normalized

    return content


def _try_normalize_json(content: str) -> Optional[str]:
    """Try all known JSON chat schemas."""

    normalized = _try_gemini_jsonl(content)
    if normalized:
        return normalized

    normalized = _try_claude_code_jsonl(content)
    if normalized:
        return normalized

    normalized = _try_codex_jsonl(content)
    if normalized:
        return normalized

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None

    for parser in (_try_claude_ai_json, _try_chatgpt_json, _try_slack_json):
        normalized = parser(data)
        if normalized:
            return normalized

    return None


def _try_gemini_jsonl(content: str) -> Optional[str]:
    """Gemini CLI JSONL sessions with a session_metadata sentinel."""
    lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
    messages = []
    seen_metadata = False
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type", "")
        if entry_type == "session_metadata":
            seen_metadata = True
            continue
        if not seen_metadata or entry_type == "message_update":
            continue
        if entry_type not in {"user", "gemini"}:
            continue
        text = _extract_content(entry.get("message", {}).get("content", entry.get("content", "")))
        if not text:
            continue
        role = "user" if entry_type == "user" else "assistant"
        messages.append((role, text))
    if seen_metadata and len(messages) >= 2:
        return _messages_to_transcript(messages)
    return None


def _try_claude_code_jsonl(content: str) -> Optional[str]:
    """Claude Code JSONL sessions."""
    lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
    messages = []
    tool_names: dict[str, str] = {}
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        msg_type = entry.get("type", "")
        message = entry.get("message", {})
        if msg_type in ("human", "user"):
            content_blocks = message.get("content", "")
            text = _extract_claude_code_content(content_blocks, tool_names=tool_names)
            if text:
                if _is_tool_result_only(content_blocks):
                    if messages and messages[-1][0] == "assistant":
                        prev_role, prev_text = messages[-1]
                        messages[-1] = (prev_role, prev_text.rstrip() + "\n\n" + text)
                    continue
                if text.startswith("Tool result") and messages and messages[-1][0] == "assistant":
                    prev_role, prev_text = messages[-1]
                    messages[-1] = (prev_role, prev_text.rstrip() + "\n\n" + text)
                else:
                    messages.append(("user", text))
        elif msg_type == "assistant":
            text = _extract_claude_code_content(message.get("content", ""), tool_names=tool_names)
            if text:
                messages.append(("assistant", text))
    if len(messages) >= 2:
        return _messages_to_transcript(messages)
    return None


def _try_codex_jsonl(content: str) -> Optional[str]:
    """OpenAI Codex CLI sessions (~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl).

    Uses only event_msg entries (user_message / agent_message) which represent
    the canonical conversation turns. response_item entries are skipped because
    they include synthetic context injections and duplicate the real messages.
    """
    lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
    messages = []
    has_session_meta = False
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue

        entry_type = entry.get("type", "")
        if entry_type == "session_meta":
            has_session_meta = True
            continue

        if entry_type != "event_msg":
            continue

        payload = entry.get("payload", {})
        if not isinstance(payload, dict):
            continue

        payload_type = payload.get("type", "")
        msg = payload.get("message")
        if not isinstance(msg, str):
            continue
        text = msg.strip()
        if not text:
            continue

        if payload_type == "user_message":
            messages.append(("user", text))
        elif payload_type == "agent_message":
            messages.append(("assistant", text))

    if len(messages) >= 2 and has_session_meta:
        return _messages_to_transcript(messages)
    return None


def _try_claude_ai_json(data) -> Optional[str]:
    """Claude.ai JSON export: flat messages list or privacy export with chat_messages."""
    if isinstance(data, dict):
        data = data.get("messages", data.get("chat_messages", []))
    if not isinstance(data, list):
        return None

    # Privacy export: array of conversation objects with chat_messages inside each
    if data and isinstance(data[0], dict) and "chat_messages" in data[0]:
        all_messages = []
        for convo in data:
            if not isinstance(convo, dict):
                continue
            chat_msgs = convo.get("chat_messages", [])
            for item in chat_msgs:
                if not isinstance(item, dict):
                    continue
                role = item.get("role", "")
                text = _extract_content(item.get("content", ""))
                if role in ("user", "human") and text:
                    all_messages.append(("user", text))
                elif role in ("assistant", "ai") and text:
                    all_messages.append(("assistant", text))
        if len(all_messages) >= 2:
            return _messages_to_transcript(all_messages)
        return None

    # Flat messages list
    messages = []
    for item in data:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "")
        text = _extract_content(item.get("content", ""))
        if role in ("user", "human") and text:
            messages.append(("user", text))
        elif role in ("assistant", "ai") and text:
            messages.append(("assistant", text))
    if len(messages) >= 2:
        return _messages_to_transcript(messages)
    return None


def _try_chatgpt_json(data) -> Optional[str]:
    """ChatGPT conversations.json with mapping tree."""
    if not isinstance(data, dict) or "mapping" not in data:
        return None
    mapping = data["mapping"]
    messages = []
    # Find root: prefer node with parent=None AND no message (synthetic root)
    root_id = None
    fallback_root = None
    for node_id, node in mapping.items():
        if node.get("parent") is None:
            if node.get("message") is None:
                root_id = node_id
                break
            elif fallback_root is None:
                fallback_root = node_id
    if not root_id:
        root_id = fallback_root
    if root_id:
        current_id = root_id
        visited = set()
        while current_id and current_id not in visited:
            visited.add(current_id)
            node = mapping.get(current_id, {})
            msg = node.get("message")
            if msg:
                role = msg.get("author", {}).get("role", "")
                content = msg.get("content", {})
                parts = content.get("parts", []) if isinstance(content, dict) else []
                text = " ".join(str(p) for p in parts if isinstance(p, str) and p).strip()
                if role == "user" and text:
                    messages.append(("user", text))
                elif role == "assistant" and text:
                    messages.append(("assistant", text))
            children = node.get("children", [])
            current_id = children[0] if children else None
    if len(messages) >= 2:
        return _messages_to_transcript(messages)
    return None


def _try_slack_json(data) -> Optional[str]:
    """
    Slack channel export: [{"type": "message", "user": "...", "text": "..."}]
    Optimized for 2-person DMs. In channels with 3+ people, alternating
    speakers are labeled user/assistant to preserve the exchange structure.
    """
    if not isinstance(data, list):
        return None
    messages = []
    seen_users = {}
    last_role = None
    for item in data:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        user_id = _sanitize_speaker_id(item.get("user", item.get("username", "")))
        text = item.get("text", "").strip()
        if not text or not user_id:
            continue
        if user_id not in seen_users:
            # Alternate roles so exchange chunking works with any number of speakers
            if not seen_users:
                seen_users[user_id] = "user"
            elif last_role == "user":
                seen_users[user_id] = "assistant"
            else:
                seen_users[user_id] = "user"
        last_role = seen_users[user_id]
        messages.append((seen_users[user_id], f"[{user_id}] {text}"))
    if len(messages) >= 2:
        return (
            _messages_to_transcript(messages)
            + "\nSlack provenance: user/assistant roles are positional; original speaker IDs are preserved in brackets.\n"
        )
    return None


def _extract_content(content) -> str:
    """Pull text from content — handles str, list of blocks, or dict."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and (item.get("type") == "text" or "text" in item):
                parts.append(item.get("text", ""))
        return " ".join(parts).strip()
    if isinstance(content, dict):
        return content.get("text", "").strip()
    return ""


def _is_tool_result_only(content) -> bool:
    if not isinstance(content, list):
        return False
    saw_tool_result = False
    for item in content:
        if isinstance(item, dict) and item.get("type") == "tool_result":
            saw_tool_result = True
            continue
        if isinstance(item, str) and not item.strip():
            continue
        return False
    return saw_tool_result


def _extract_claude_code_content(content, tool_names: Optional[dict[str, str]] = None) -> str:
    if isinstance(content, str):
        return _strip_noise(content)
    if not isinstance(content, list):
        return _extract_content(content)
    tool_names = tool_names if tool_names is not None else {}
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(_strip_noise(item))
        elif isinstance(item, dict):
            kind = item.get("type")
            if kind == "text":
                parts.append(_strip_noise(item.get("text", "")))
            elif kind == "tool_use":
                tool_id = item.get("id")
                tool_name = item.get("name") or item.get("tool_name") or "tool"
                tool_names["__last__"] = str(tool_name)
                if tool_id:
                    tool_names[str(tool_id)] = str(tool_name)
                parts.append(_format_tool_use(item))
            elif kind == "tool_result":
                formatted = _format_tool_result(item, tool_names=tool_names)
                if formatted:
                    parts.append(formatted)
    return "\n".join(p for p in parts if p).strip()


def _format_tool_use(item: dict) -> str:
    name = item.get("name") or item.get("tool_name") or "tool"
    data = item.get("input") or {}
    if name == "Bash":
        detail = data.get("command", "")
    elif name == "Read":
        path = data.get("file_path") or data.get("path") or ""
        rng = ""
        if data.get("offset") is not None or data.get("limit") is not None:
            rng = f" offset={data.get('offset', 0)} limit={data.get('limit')}"
        detail = f"{path}{rng}".strip()
    elif name in {"Grep", "Glob"}:
        detail = data.get("pattern", "")
    elif name in {"Edit", "Write"}:
        detail = data.get("file_path") or data.get("path") or ""
    else:
        detail = " ".join(f"{k}={v}" for k, v in sorted(data.items())[:4])
    return f"Tool use: {name} {detail}".strip()


def _cap_head_tail(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    head_len = max_chars // 2 - 200
    tail_len = max_chars // 2 - 200
    head = text[:head_len].rstrip()
    tail = text[-tail_len:].lstrip()
    return f"{head}\n...[tool result truncated]...\n{tail}"


def _cap_match_lines(text: str, visible_each_side: int = 20) -> str:
    lines = text.splitlines()
    cap = visible_each_side * 2
    if len(lines) <= cap:
        return text
    omitted = len(lines) - cap
    return "\n".join(
        lines[:visible_each_side]
        + [f"...[{omitted} matches omitted]..."]
        + lines[-visible_each_side:]
    )


def _format_tool_result(item: dict, tool_names: Optional[dict[str, str]] = None) -> str:
    tool_use_id = item.get("tool_use_id") or item.get("id")
    tool_name = ""
    if tool_use_id and tool_names:
        tool_name = tool_names.get(str(tool_use_id), "")
    tool_name = tool_name or item.get("name") or item.get("tool_name")
    if not tool_name and tool_names:
        tool_name = tool_names.get("__last__")
    tool_name = tool_name or "tool"
    if tool_name in {"Read", "Edit", "Write"}:
        return ""
    content = item.get("content", "")
    text = _extract_content(content) if not isinstance(content, str) else content
    text = _strip_noise(text).strip()
    if not text:
        return ""
    if tool_name in {"Grep", "Glob"}:
        text = _cap_match_lines(text)
    else:
        text = _cap_head_tail(text)
    return f"Tool result ({tool_name}):\n{text}"


_NOISE_LINES = (
    re.compile(r"^\s*Mnemion auto-save checkpoint\b.*$", re.IGNORECASE),
    re.compile(r"^\s*MemPalace auto-save checkpoint\b.*$", re.IGNORECASE),
    re.compile(r"^\s*Claude Code system prompt\b.*$", re.IGNORECASE),
)


def _strip_noise(text: str) -> str:
    lines = []
    for line in str(text).splitlines():
        if any(pattern.match(line) for pattern in _NOISE_LINES):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _sanitize_speaker_id(value: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f\]\[]", "_", str(value).strip())
    return cleaned[:80] or "unknown"


def _messages_to_transcript(messages: list, spellcheck: bool = True) -> str:
    """Convert [(role, text), ...] to transcript format with > markers."""
    if spellcheck:
        try:
            from mnemion.spellcheck import spellcheck_user_text

            _fix = spellcheck_user_text
        except ImportError:
            _fix = None
    else:
        _fix = None

    lines = []
    i = 0
    while i < len(messages):
        role, text = messages[i]
        if role == "user":
            if _fix is not None:
                text = _fix(text)
            lines.append(f"> {text}")
            if i + 1 < len(messages) and messages[i + 1][0] == "assistant":
                lines.append(messages[i + 1][1])
                i += 2
            else:
                i += 1
        else:
            lines.append(text)
            i += 1
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python normalize.py <filepath>")
        sys.exit(1)
    filepath = sys.argv[1]
    result = normalize(filepath)
    quote_count = sum(1 for line in result.split("\n") if line.strip().startswith(">"))
    print(f"\nFile: {os.path.basename(filepath)}")
    print(f"Normalized: {len(result)} chars | {quote_count} user turns detected")
    print("\n--- Preview (first 20 lines) ---")
    print("\n".join(result.split("\n")[:20]))
