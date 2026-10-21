"""Opt-in JSONL capture: complete records, bounded fragments and per-file scopes."""

from contextlib import contextmanager
import hashlib
import json
import os
import re
import time
from urllib.parse import quote
from uuid import uuid4

from ..capture_coverage import SelectionCounts
from ..conversations import VERSION, parse
from ..service.connector_models import ConnectorItemInput
from ..version import __version__
from .conversation_state import capture_state
from .protocol import Document, Scope
from .providers import ProviderError, filesystem_paths, private_vault_content
from .source_files import SourceReadError, open_selected

CAPTURE = "mnemion-live-jsonl-v1"
BUFFER_BYTES = 65536


def stat_value(info):
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "birth": getattr(info, "st_birthtime_ns", 0),
        "size": info.st_size,
        "mtime": info.st_mtime_ns,
        "ctime": info.st_ctime_ns,
    }


def same_file(first, second):
    return (first["device"], first["inode"], first.get("birth", 0)) == (
        second["device"],
        second["inode"],
        second.get("birth", 0),
    )


def file_mark(value):
    return hashlib.sha256(
        f"{value['device']}:{value['inode']}:{value.get('birth', 0)}".encode()
    ).hexdigest()[:32]


def checkpoint_identity(value):
    if not isinstance(value, str) or len(value) > 1024 or not value.startswith("jsonl:v1:"):
        return None
    try:
        state = json.loads(value[9:])
        if not isinstance(state, dict) or any(
            not isinstance(state.get(key), str) or not re.fullmatch(r"[a-f0-9]{32}", state[key])
            for key in ("generation", "file")
        ):
            return None
        if (
            any(type(state.get(key)) is not int for key in ("captured", "observed"))
            or not 0 <= state["captured"] <= state["observed"] <= 1_000_000_000_000
        ):
            return None
        if state.get("captured_sha256") is not None and (
            not isinstance(state["captured_sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", state["captured_sha256"])
        ):
            return None
        return state
    except (ValueError, RecursionError):
        return None


class ConversationProvider:
    access_mode = "published"

    def __init__(self, config):
        self.config = config
        self.root = config.path.expanduser().resolve()
        self.paths = {}

    def scopes(self):
        # Each selected file has its own authorization lease and failure state.
        # A directory/catalog failure still prevents authoritative removals.
        self.paths = {
            "conversation:"
            + hashlib.sha256((self.config.scope_id + "\0" + path).encode()).hexdigest(): path
            for path in filesystem_paths(self.config, verify_files=False)
            if path.lower().endswith(".jsonl")
        }
        return list(self.paths)

    def access(self, identifier):
        if identifier not in self.paths:
            raise ProviderError("conversation_source_unavailable", access_lost=True)
        try:
            with open_selected(self.root, self.paths[identifier]):
                pass
        except SourceReadError as exc:
            raise ProviderError(exc.code, access_lost=True) from None
        return Scope(
            identifier,
            (self.config.name + " · " + self.paths[identifier])[:200],
            self.config.members,
        )

    @contextmanager
    def snapshot(self, identifier, checkpoint):
        owner = {
            "format": CAPTURE,
            "root": str(self.root),
            "scope_id": self.config.scope_id,
        }
        with capture_state(self.config.state_directory, owner, identifier) as state:
            yield ConversationSnapshot(self, identifier, state, checkpoint)


class ConversationSnapshot:
    def __init__(self, provider, identifier, state, remote_checkpoint):
        self.provider, self.config = provider, provider.config
        self.identifier, self.state = identifier, state
        self.relative = provider.paths[identifier]
        self.scan_id = uuid4().hex
        self.checkpoint = "jsonl:" + self.scan_id
        self.resumable_capture = getattr(state, "resumable_capture", False)
        self.deferred = False
        # An upgraded renderer re-examines the source. Stable output still keeps
        # the same evidence revisions, so an upgrade cannot force re-embedding.
        self.settings = hashlib.sha256(
            json.dumps(
                [
                    CAPTURE,
                    VERSION,
                    __version__,
                    self.config.normalize_conversations,
                    self.config.capture_mode,
                    self.config.segment_bytes,
                    self.config.segment_records,
                    *([self.config.capture_policy.revision] if self.config.capture_policy else []),
                    *(["retained-window-v1"] if self.resumable_capture else []),
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        self.previous = state.read()
        if self.previous and "scan_complete" in self.previous:
            if type(self.previous["scan_complete"]) is not bool:
                raise ProviderError("capture_checkpoint_invalid")
        self.observe_selection = getattr(state, "observes_selection", False)
        if self.observe_selection and self.previous and "accounting" in self.previous:
            accounting = self.previous["accounting"]
            try:
                if (
                    set(accounting) != {"version", "sealed", "current"}
                    or accounting["version"] != 1
                ):
                    raise ValueError()
                for value in (accounting["sealed"], accounting["current"]):
                    SelectionCounts.model_validate(value)
                if accounting["sealed"]["lines"] != self.previous["sealed_lines"]:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise ProviderError("capture_checkpoint_invalid") from None
        self.remote_identity = checkpoint_identity(remote_checkpoint)
        self.trusted = bool(
            self.previous
            and self.previous["settings"] == self.settings
            and self.previous["checkpoint"] == remote_checkpoint
            and (not self.observe_selection or "accounting" in self.previous)
        )
        self.selection = SelectionCounts().model_dump()
        self.deadline = time.monotonic() + self.config.max_scan_seconds
        self.ready = None
        self.report = {
            "format": CAPTURE,
            "capture_mode": self.config.capture_mode,
            "bytes_read": 0,
            "segments_reused": 0,
            "segments_rendered": 0,
            "records_rendered": 0,
        }

    def _check_time(self):
        if time.monotonic() > self.deadline:
            raise ProviderError("conversation_scan_deadline")

    def _hash_prefix(self, stream, length):
        stream.seek(0)
        digest, left, progress = hashlib.sha256(), length, 0
        while left:
            self._check_time()
            data = stream.read(min(BUFFER_BYTES, left))
            if not data:
                raise ProviderError("source_changed_during_read")
            self.report["bytes_read"] += len(data)
            digest.update(data)
            left -= len(data)
            progress += len(data)
            if progress >= 4 * 1024 * 1024:
                progress = 0
                yield None  # Renew service/ACL leases during long verification.
        return digest

    def _retain(self, before):
        if self.resumable_capture:
            self._check_time()
            self.report["segments_reused"] += self.state.retain_prefix(before, self.scan_id)
            self._limit_segments()
            return
        for refs in self.state.references(before, self.scan_id):
            self._check_time()
            self.report["segments_reused"] += 1
            self._limit_segments()
            for value in refs:
                yield ConnectorItemInput(action="retain", **value)

    def _limit_segments(self):
        if (
            self.report["segments_reused"] + self.report["segments_rendered"]
            > self.config.max_segments
        ):
            raise ProviderError("conversation_segment_limit")

    def _row(self, raw, position):
        try:
            text = raw.decode("utf-8-sig" if position == 0 else "utf-8")
        except UnicodeError:
            raise ProviderError("source_is_not_utf8_text") from None
        if not text.strip():
            return None
        if private_vault_content(text):
            raise ProviderError("conversation_contains_private_control")
        try:
            value = json.loads(text)
        except (ValueError, RecursionError):
            raise ProviderError("conversation_jsonl_record_invalid") from None
        if isinstance(value, dict) and value.get("format") in (
            "mnemion-memory-journal",
            "mnemion-memory-journal-catalog",
        ):
            # Journal denials require the original complete cross-file catalog.
            raise ProviderError("journal_requires_complete_connector")
        return value

    def _visible_row(self, row, position):
        if not isinstance(row, dict) or row.get("method") != "session/update":
            return True
        params = row.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("update"), dict):
            return True
        update = params["update"]
        if update.get("sessionUpdate") not in ("user_message_chunk", "agent_message_chunk"):
            return True
        content = update.get("content")
        if (
            not isinstance(content, dict)
            or content.get("type") != "text"
            or not isinstance(content.get("text"), str)
        ):
            return True
        event = update.get("eventId", row.get("eventId"))
        if event is None:
            return True
        session = params.get("sessionId", hashlib.sha256(self.identifier.encode()).hexdigest())
        if not isinstance(session, str) or not session.strip() or len(session) > 1024:
            raise ProviderError("conversation_session_invalid")
        if type(event) not in {str, int} or len(str(event)) > 1024:
            raise ProviderError("conversation_event_invalid")
        digest = hashlib.sha256(
            json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return self.state.event(session, json.dumps(event), digest, position)

    def _segment(self, raw, rows, start, record_start, record_end, context):
        self.report["segments_rendered"] += 1
        self._limit_segments()
        digest = hashlib.sha256(raw).hexdigest()
        external = self.identifier + ":" + self.generation + ":bytes:" + str(start)
        uri = (
            "mnemion-source://conversations/"
            + quote(self.config.scope_id, safe="")
            + "/"
            + quote(self.relative, safe="/")
        )
        metadata = {
            "path": self.relative,
            "capture": CAPTURE,
            "source_generation": self.generation,
            "source_byte_start": start,
            "source_byte_end": start + len(raw),
            "source_line_start": record_start,
            "source_line_end": record_end,
            "source_segment_sha256": digest,
            "source_fragment": True,
        }
        if self.config.capture_policy:
            metadata["capture_policy_revision"] = self.config.capture_policy.revision
        text = raw.decode("utf-8-sig" if start == 0 else "utf-8")
        document = Document(external, digest, self.relative, text, uri, metadata=metadata)
        messages_only = self.config.capture_mode == "messages"
        items = [] if messages_only else list(document.items())
        outcomes = [] if self.observe_selection and messages_only else None
        if self.config.normalize_conversations:
            visible = rows
            if context:
                visible = [{"type": "session_meta", "payload": {"id": context["id"]}}, *rows]
            for transcript in parse(
                json.dumps(visible, ensure_ascii=False),
                self.identifier,
                messages_only=messages_only,
                selection=outcomes,
            ):
                provenance = (
                    {
                        "raw_source_external_id": external,
                        "raw_document_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    }
                    if not messages_only
                    else {
                        "capture_mode": "messages",
                        "raw_evidence_stored": False,
                        "source_document_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    }
                )
                companion = Document(
                    external + "#conversation:" + transcript.identifier,
                    hashlib.sha256(
                        (
                            digest
                            + VERSION
                            + transcript.text
                            + json.dumps(context, sort_keys=True)
                            + ("messages-only-v1" if messages_only else "")
                        ).encode()
                    ).hexdigest(),
                    transcript.title + " · conversation fragment",
                    transcript.text,
                    uri,
                    metadata={
                        **metadata,
                        "projection": VERSION,
                        "conversation_format": transcript.format,
                        "conversation_id": transcript.identifier[:512],
                        "conversation_turn_fragments": transcript.turns,
                        **provenance,
                        "context_header": context,
                    },
                )
                items.extend(companion.items())
        if self.observe_selection:
            lines = record_end - record_start
            values = (outcomes[1:] if context and outcomes is not None else outcomes) or []
            chosen = values.count("selected") if messages_only else lines
            unsupported = (
                (
                    values.count("unsupported")
                    + (len(rows) if not self.config.normalize_conversations else 0)
                )
                if messages_only
                else 0
            )
            additions = SelectionCounts(
                lines=lines,
                selected=chosen,
                unsupported=unsupported,
                omitted=lines - chosen - unsupported,
            ).model_dump()
            for field, value in additions.items():
                self.selection[field] += value
        known = self.state.segment(start, items, self.scan_id, reuse=self.trusted)
        for item in items:
            if (item.external_id, item.revision) in known:
                yield ConnectorItemInput(
                    external_id=item.external_id, revision=item.revision, action="retain"
                )
            else:
                yield item

    def items(self):
        try:
            with open_selected(self.provider.root, self.relative) as stream:
                before = stat_value(os.fstat(stream.fileno()))
                self.report["observed_size_bytes"] = before["size"]
                if before["size"] > self.config.max_file_bytes:
                    raise ProviderError("conversation_file_limit")
                previous = self.previous if self.trusted else None
                change = "initial"
                if previous:
                    old = previous["stat"]
                    change = (
                        "rotation"
                        if not same_file(old, before)
                        else "truncation"
                        if before["size"] < previous["complete_end"]
                        else "tail_reset"
                        if before["size"] < old["size"]
                        else "unchanged"
                        if old == before
                        else "append"
                        if before["size"] > old["size"]
                        else "rewrite"
                    )
                self.generation = hashlib.sha256(
                    (self.identifier + json.dumps(before, sort_keys=True)).encode()
                ).hexdigest()[:32]
                if previous and change not in {"rotation", "truncation"}:
                    self.generation = previous["generation"]
                elif (
                    not previous
                    and self.previous
                    and same_file(self.previous["stat"], before)
                    and before["size"] >= self.previous["complete_end"]
                ):
                    self.generation = self.previous["generation"]
                elif not previous and self.remote_identity:
                    remote = self.remote_identity
                    if remote["file"] == file_mark(before) and before["size"] >= remote["captured"]:
                        self.generation = remote["generation"]
                    elif before["size"] >= remote["captured"] and remote.get("captured_sha256"):
                        restored = yield from self._hash_prefix(stream, remote["captured"])
                        if restored.hexdigest() == remote["captured_sha256"]:
                            self.generation = remote["generation"]
                            change = "restored"
                        else:
                            change = "rotation"
                    else:
                        change = "rotation" if remote["file"] != file_mark(before) else "truncation"
                self.report["change"] = change
                self.report["generation"] = self.generation
                if previous and change == "unchanged" and previous.get("scan_complete", True):
                    yield from self._retain(previous["complete_end"] + 1)
                    # An unchanged stat is rechecked through a fresh source handle.
                    after = self._current(before, previous["complete_end"])
                    if after != before:
                        raise ProviderError("source_changed_during_read")
                    self.ready = {**previous, "checkpoint": self.checkpoint}
                    self._report_capture(after, previous["complete_end"])
                    return
                if previous and change == "unchanged":
                    self.report["change"] = "resume"

                start, record_start, context = 0, 0, None
                digest = hashlib.sha256()
                if previous and change not in {"rotation", "truncation"}:
                    candidate = previous["sealed_end"]
                    if candidate <= before["size"]:
                        digest = yield from self._hash_prefix(stream, candidate)
                        if digest.hexdigest() == previous["prefix_sha256"]:
                            start = candidate
                            record_start = previous["sealed_lines"]
                            context = previous["context"]
                            if self.observe_selection:
                                self.selection = dict(previous["accounting"]["sealed"])
                            yield from self._retain(start)
                        else:
                            self.report["change"] = "rewrite"
                            digest = hashlib.sha256()
                self.state.rewind_events(start)
                stream.seek(start)
                offset, line_number = start, record_start
                block, rows, block_size = [], [], 0
                block_start, block_line, block_context = start, record_start, context
                prefix_digest = digest.copy()
                sealed_selection = dict(self.selection)
                while offset < before["size"]:
                    self._check_time()
                    raw = stream.readline(
                        min(self.config.max_record_bytes + 1, before["size"] - offset)
                    )
                    self.report["bytes_read"] += len(raw)
                    if not raw:
                        raise ProviderError("source_changed_during_read")
                    if len(raw) > self.config.max_record_bytes:
                        raise ProviderError("conversation_record_limit")
                    if not raw.endswith(b"\n"):
                        break  # Even valid JSON without LF may still be growing.
                    if block and (
                        block_size + len(raw) > self.config.segment_bytes
                        or line_number - block_line >= self.config.segment_records
                    ):
                        yield from self._segment(
                            b"".join(block),
                            rows,
                            block_start,
                            block_line,
                            line_number,
                            block_context,
                        )
                        block, rows, block_size = [], [], 0
                        block_start, block_line, block_context = offset, line_number, context
                        prefix_digest = digest.copy()
                        sealed_selection = dict(self.selection)
                        if self.resumable_capture and self.state.window_reached(
                            segments=self.report["segments_rendered"],
                            new_bytes=offset - start,
                            read_bytes=self.report["bytes_read"],
                            remaining_seconds=self.deadline - time.monotonic(),
                            scan_seconds=self.config.max_scan_seconds,
                        ):
                            # The next line has only been read ahead. Stop at
                            # the existing fragment boundary; its text, event
                            # identity and accounting have not been consumed.
                            self.deferred = True
                            break
                    row = self._row(raw, offset)
                    if (
                        self.config.normalize_conversations
                        and row is not None
                        and self._visible_row(row, offset)
                    ):
                        rows.append(row)
                    if (
                        self.config.normalize_conversations
                        and isinstance(row, dict)
                        and row.get("type") == "session_meta"
                    ):
                        payload = row.get("payload")
                        identifier = payload.get("id") if isinstance(payload, dict) else None
                        if identifier is not None:
                            if not isinstance(identifier, str) or len(identifier) > 1024:
                                raise ProviderError("conversation_session_invalid")
                            context = {
                                "id": identifier,
                                "byte_offset": offset,
                                "sha256": hashlib.sha256(raw).hexdigest(),
                            }
                    block.append(raw)
                    block_size += len(raw)
                    digest.update(raw)
                    offset += len(raw)
                    line_number += 1
                    self.report["records_rendered"] += 1
                if block:
                    yield from self._segment(
                        b"".join(block), rows, block_start, block_line, line_number, block_context
                    )
                after = self._current(before, offset)
                if after != before:
                    # Appends may continue. Verify the captured prefix again;
                    # growth alone never proves that earlier bytes were immutable.
                    current = yield from self._hash_prefix(stream, offset)
                    if current.digest() != digest.digest():
                        raise ProviderError("source_changed_during_read")
                    after = self._current(before, offset)
                self.ready = {
                    "settings": self.settings,
                    "generation": self.generation,
                    "checkpoint": self.checkpoint,
                    "stat": after,
                    "complete_end": offset,
                    "sealed_end": block_start,
                    "sealed_lines": block_line,
                    "prefix_sha256": prefix_digest.hexdigest(),
                    "complete_sha256": digest.hexdigest(),
                    "context": block_context,
                }
                if self.resumable_capture:
                    self.ready["scan_complete"] = not self.deferred
                if self.observe_selection:
                    self.ready["accounting"] = {
                        "version": 1,
                        "sealed": sealed_selection,
                        "current": SelectionCounts.model_validate(self.selection).model_dump(),
                    }
                # If bytes arrived after the frozen read boundary, force the next
                # scan to inspect them even if that file no longer changes.
                if after != before:
                    self.ready["stat"] = before
                self._report_capture(after, offset)
        except SourceReadError as exc:
            raise ProviderError(exc.code, access_lost=True) from None

    def _current(self, before, complete_end):
        with open_selected(self.provider.root, self.relative) as current:
            result = stat_value(os.fstat(current.fileno()))
        if not same_file(before, result) or result["size"] < complete_end:
            raise ProviderError("source_changed_during_read")
        return result

    def _report_capture(self, stat, complete_end):
        self.report.update(
            observed_size_bytes=stat["size"],
            captured_prefix_bytes=complete_end,
            pending_bytes=max(0, stat["size"] - complete_end),
            inventory="complete_record_prefix",
        )
        if self.resumable_capture:
            self.report.update(
                scan_complete=not self.deferred,
                inventory="bounded_record_prefix" if self.deferred else "complete_record_prefix",
            )
        if self.observe_selection:
            self.report["selection"] = self.ready["accounting"]["current"]
        # Only bounded identity/counters and a capture digest travel in the
        # scope checkpoint, never the source body. A replacement device can
        # verify that its copied prefix retains the original evidence.
        # The final empty page stores them after verification; finish commits
        # them atomically with the completed inventory for app/agent monitoring.
        self.checkpoint = "jsonl:v1:" + json.dumps(
            {
                "id": self.scan_id,
                "generation": self.generation,
                "file": file_mark(stat),
                "captured": complete_end,
                "observed": stat["size"],
                "read": self.report["bytes_read"],
                "reused": self.report["segments_reused"],
                "rendered": self.report["segments_rendered"],
                "capture_mode": self.config.capture_mode,
                **(
                    {"captured_sha256": self.ready["complete_sha256"]}
                    if self.ready.get("complete_sha256")
                    else {}
                ),
            },
            separators=(",", ":"),
        )
        self.ready["checkpoint"] = self.checkpoint

    def acknowledge(self):
        if self.ready is None:
            raise ProviderError("conversation_inventory_incomplete")
        self.state.commit(self.ready, self.scan_id)

    def invalidate(self):
        self.state.invalidate()
