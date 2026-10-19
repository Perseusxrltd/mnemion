"""Lossless companions for selected chat exports; raw files remain the evidence archive.

Rendering never spell-corrects, invents speakers, executes tools, or runs an LLM.
Unknown valid JSON remains available through the ordinary raw-file connector.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

VERSION = "mnemion-conversation-v1"


class ConversationError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Transcript:
    identifier: str
    title: str
    format: str
    text: str
    turns: int


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for item in value if (part := _text(item)))
    if isinstance(value, dict):
        if value.get("type") in {"tool_use", "tool_result", "thinking", "image"}:
            return ""
        return _text(value.get("text", value.get("parts", "")))
    return ""


def _transcript(identifier, title, fmt, turns) -> Transcript | None:
    rendered = []
    for speaker, text, timestamp in turns:
        if not text.strip():
            continue
        # Labels occupy one line; text is preserved verbatim beneath them.
        label = str(speaker).replace("\n", " ").replace("\r", " ")[:300]
        stamp = str(timestamp).replace("\n", " ").replace("\r", " ")[:100] if timestamp else ""
        rendered.append(f"[{label}{' · ' + stamp if stamp else ''}]\n{text}")
    if not rendered:
        return None
    return Transcript(str(identifier), str(title)[:300], fmt, "\n\n".join(rendered), len(rendered))


def _chatgpt(conversation: dict, fallback: str) -> Transcript | None:
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        raise ConversationError("conversation_mapping_invalid")
    current = conversation.get("current_node")
    if current is None:
        # Old exports may lack the active leaf. Do not silently choose a branch
        # and present it as the user's final conversation.
        children = {
            str(child)
            for row in mapping.values()
            if isinstance(row, dict)
            for child in (row.get("children") or [])
        }
        leaves = [
            key for key, row in mapping.items() if isinstance(row, dict) and not row.get("children")
        ]
        if len(leaves) != 1:
            return None  # The complete branching archive is still imported raw.
        current = leaves[0]
        if children and current not in children:
            raise ConversationError("conversation_mapping_invalid")
    path, seen = [], set()
    while current is not None:
        if (
            not isinstance(current, str)
            or current in seen
            or current not in mapping
            or not isinstance(mapping[current], dict)
        ):
            raise ConversationError("conversation_mapping_invalid")
        seen.add(current)
        node = mapping[current]
        message = node.get("message")
        if isinstance(message, dict):
            author = message.get("author") or {}
            role = author.get("role") if isinstance(author, dict) else None
            if role in {"user", "assistant", "system", "developer"}:
                path.append((role, _text(message.get("content")), message.get("create_time")))
        current = node.get("parent")
    return _transcript(
        conversation.get("id", conversation.get("conversation_id", fallback)),
        conversation.get("title") or "ChatGPT conversation",
        "chatgpt",
        reversed(path),
    )


def _acp_sessions(rows, fallback):
    """Grok Build and other ACP session/update logs, preserving streamed text."""
    sessions = {}

    def flush(session):
        current = session.pop("current", None)
        if current is None:
            return
        first, last = current["first"], current["last"]
        stamp = f"{first} → {last}" if first and last and first != last else first or last
        session["turns"].append((current["role"], "".join(current["parts"]), stamp))

    for row in rows:
        if not isinstance(row, dict) or row.get("method") != "session/update":
            continue
        params = row.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("update"), dict):
            continue
        update = params["update"]
        kind = update.get("sessionUpdate")
        if not isinstance(kind, str):
            continue
        role = {"user_message_chunk": "user", "agent_message_chunk": "assistant"}.get(kind)
        identifier = params.get("sessionId", fallback)
        if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 1024:
            raise ConversationError("conversation_session_invalid")
        session = sessions.setdefault(identifier, {"turns": [], "seen": {}})
        if role is None:
            if kind in {
                "tool_call",
                "tool_call_update",
                "agent_thought_chunk",
                "turn_end",
                "message_end",
                "session_end",
            }:
                flush(session)
            continue
        content = update.get("content")
        if (
            not isinstance(content, dict)
            or content.get("type") != "text"
            or not isinstance(content.get("text"), str)
        ):
            continue  # Tools, thought, resource/image blocks and status are not spoken text.
        value = content["text"]
        event_id = update.get("eventId", row.get("eventId"))
        if event_id is not None:
            if type(event_id) not in {str, int} or len(str(event_id)) > 1024:
                raise ConversationError("conversation_event_invalid")
            key = (type(event_id).__name__, event_id)
            digest = hashlib.sha256(
                json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            prior = session["seen"].get(key)
            if prior is not None:
                if prior != digest:
                    raise ConversationError("conversation_event_conflict")
                continue
            session["seen"][key] = digest
        if not value:
            continue
        message_id = update.get("messageId")
        if message_id is not None and (not isinstance(message_id, str) or len(message_id) > 1024):
            raise ConversationError("conversation_message_invalid")
        current = session.get("current")
        if current and (current["role"] != role or current["message_id"] != message_id):
            flush(session)
            current = None
        stamp = row.get("timestamp")
        if current is None:
            current = {
                "role": role,
                "message_id": message_id,
                "parts": [],
                "first": stamp,
                "last": stamp,
            }
            session["current"] = current
        current["parts"].append(value)
        if stamp:
            current["first"] = current["first"] or stamp
            current["last"] = stamp
    result = []
    for identifier, session in sessions.items():
        flush(session)
        transcript = _transcript(identifier, "Agent conversation", "acp-session", session["turns"])
        if transcript:
            result.append(transcript)
    return result


def parse(text: str, source_id: str) -> list[Transcript]:
    """Parse complete JSON/JSONL only. In-progress files fail without pruning a scan."""
    try:
        data = json.loads(text)
        rows = data if isinstance(data, list) else [data]
    except (json.JSONDecodeError, RecursionError):
        try:
            # JSONL records end at LF; Unicode separators are valid string content.
            rows = [json.loads(line) for line in text.split("\n") if line.strip()]
        except (json.JSONDecodeError, RecursionError):
            raise ConversationError("conversation_json_incomplete_or_invalid") from None
        data = rows
    if len(rows) > 100000:
        raise ConversationError("conversation_turn_limit")
    fallback = hashlib.sha256(source_id.encode()).hexdigest()
    result = []

    def add(value):
        if value:
            result.append(value)

    if any(isinstance(row, dict) and row.get("method") == "session/update" for row in rows):
        return _acp_sessions(rows, fallback)

    if any(isinstance(row, dict) and row.get("type") == "session_meta" for row in rows):
        turns, identifier = [], fallback
        for row in rows:
            if not isinstance(row, dict):
                continue
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            if row.get("type") == "session_meta":
                identifier = payload.get("id") or identifier
            if row.get("type") == "event_msg" and payload.get("type") in {
                "user_message",
                "agent_message",
            }:
                turns.append(
                    (
                        "user" if payload["type"] == "user_message" else "assistant",
                        _text(payload.get("message")),
                        row.get("timestamp"),
                    )
                )
        add(_transcript(identifier, "Codex session", "codex", turns))
        return result

    if any(
        isinstance(row, dict)
        and row.get("type") in {"user", "human", "assistant"}
        and isinstance(row.get("message"), dict)
        for row in rows
    ):
        turns, identifier = [], fallback
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("message"), dict):
                continue
            identifier = row.get("sessionId") or identifier
            role = row.get("type")
            if role in {"user", "human", "assistant"}:
                turns.append(
                    (
                        "user" if role == "human" else role,
                        _text(row["message"].get("content")),
                        row.get("timestamp"),
                    )
                )
        add(_transcript(identifier, "Claude Code session", "claude-code", turns))
        return result

    if any(isinstance(row, dict) and "mapping" in row for row in rows):
        for index, row in enumerate(rows):
            if isinstance(row, dict) and "mapping" in row:
                add(_chatgpt(row, f"{fallback}:{index}"))
        return result

    if isinstance(data, dict) and ("chat_messages" in data or "messages" in data):
        rows = [data]
    if any(isinstance(row, dict) and ("chat_messages" in row or "messages" in row) for row in rows):
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            messages = row.get("chat_messages", row.get("messages", []))
            if not isinstance(messages, list):
                raise ConversationError("conversation_messages_invalid")
            turns = []
            for message in messages:
                if not isinstance(message, dict):
                    continue
                role = message.get("sender", message.get("role", "unknown"))
                turns.append(
                    (
                        role,
                        _text(message.get("content") or message.get("text", "")),
                        message.get("created_at"),
                    )
                )
            add(
                _transcript(
                    row.get("uuid", row.get("id", f"{fallback}:{index}")),
                    row.get("name", row.get("title", "Conversation")),
                    "claude-export",
                    turns,
                )
            )
        return result

    if any(
        isinstance(row, dict) and row.get("type") == "message" and "text" in row for row in rows
    ):
        # Preserve actual Slack identities, including multi-person conversations.
        threads = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("type") != "message":
                continue
            identifier = str(row.get("thread_ts", row.get("ts", "channel")))
            threads.setdefault(identifier, []).append(
                (
                    row.get("user", row.get("username", row.get("bot_id", "unknown"))),
                    _text(row.get("text")),
                    row.get("ts"),
                )
            )
        for identifier, turns in threads.items():
            add(_transcript(identifier, "Slack conversation", "slack-export", turns))
        return result

    if rows and all(isinstance(row, dict) and "role" in row and "content" in row for row in rows):
        add(
            _transcript(
                fallback,
                "Conversation",
                "messages",
                [(row["role"], _text(row["content"]), row.get("timestamp")) for row in rows],
            )
        )
    return result
