"""Bounded local capture preview. No credentials, model calls or saved content."""

import fnmatch
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Literal

from pydantic import Field, model_validator

from .capture_coverage import Count, SelectionCounts, utc_now
from .capture_identity import canonical_capture_json
from .capture_policy import CapturePolicy
from .connectors.config import ConversationConfig
from .connectors.providers import private_vault_content, selected
from .connectors.source_files import SourceReadError, open_selected
from .conversations import parse
from .service.models import Command

MAX_FILES = 8
MAX_ENTRIES = 10000
MAX_BYTES = 1024 * 1024
FILE_BYTES = 128 * 1024
MAX_SECONDS = 3


class PreviewSelection(Command):
    path: str = Field(min_length=1, max_length=4096)
    capture_mode: Literal["messages", "complete"]
    capture_policy: CapturePolicy | None = None
    keep_accepted: bool = Field(strict=True)
    memory_limit_mib: int = Field(default=256, ge=128, le=2048, strict=True)
    max_files: int = Field(default=10000, ge=1, le=100000, strict=True)
    pending_limit_mib: int = Field(default=256, ge=1, le=1024, strict=True)

    @model_validator(mode="after")
    def valid(self):
        if not Path(self.path).is_absolute() or "\x00" in self.path:
            raise ValueError("Choose an absolute conversation folder")
        if self.capture_policy is not None and (
            self.capture_policy.capture_mode != self.capture_mode
            or (self.capture_policy.retention == "until_deleted") != self.keep_accepted
        ):
            raise ValueError("Match the preview's capture and retention choices")
        return self

    @property
    def fingerprint(self):
        return hashlib.sha256(canonical_capture_json(self.model_dump(mode="json"))).hexdigest()


class PreviewFile(Command):
    path: str = Field(min_length=1, max_length=4096)
    status: Literal[
        "sampled",
        "unreadable",
        "changed",
        "too_large",
        "record_too_large",
        "private_control",
        "invalid_jsonl",
    ]
    file_bytes: Count = 0
    read_bytes: Count = 0
    prefix_bytes: Count = 0
    records: SelectionCounts = Field(default_factory=SelectionCounts)


class CapturePreview(Command):
    format: Literal["mnemion-capture-preview-v1"] = "mnemion-capture-preview-v1"
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    observed_at: str
    capture_mode: Literal["messages", "complete"]
    catalog: Literal["complete", "limited", "unavailable"]
    visited_entries: int = Field(ge=0, le=MAX_ENTRIES)
    read_bytes: int = Field(ge=0, le=MAX_BYTES)
    files: list[PreviewFile] = Field(max_length=MAX_FILES)
    records: SelectionCounts
    file_limit: Literal[8] = MAX_FILES
    byte_limit: Literal[1048576] = MAX_BYTES
    attachment_binaries: Literal["not_read"] = "not_read"
    external_links: Literal["not_followed"] = "not_followed"
    hidden_reasoning: Literal["unavailable"] = "unavailable"
    field_redaction: Literal["not_supported"] = "not_supported"
    automatic_expiry: Literal["not_enabled"] = "not_enabled"
    content_saved: Literal[False] = False


def selection_for(source):
    return PreviewSelection(
        path=source.path,
        capture_mode=source.capture_mode or "complete",
        capture_policy=source.capture_policy,
        keep_accepted=bool(source.custody),
        memory_limit_mib=source.memory_limit_mib,
        max_files=source.max_files,
        pending_limit_mib=source.custody.pending_limit_mib if source.custody else 256,
    )


def normalize(root, selection, private_roots):
    from .desktop_sources import source_folder

    selection.path = str(source_folder(selection, root, private_roots))
    return selection


def _sample(config, relative, maximum):
    report = PreviewFile(path=relative, status="unreadable")
    try:
        with open_selected(config.path, relative) as stream:
            before = os.fstat(stream.fileno())
            report.file_bytes = before.st_size
            if before.st_size > config.max_file_bytes:
                report.status = "too_large"
                return report
            data = stream.read(maximum)
            report.read_bytes = len(data)
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                report.status = "changed"
                return report
        # Collection also waits for a newline before accepting a record. This
        # limited prefix never claims that the rest of the file was examined.
        prefix = data[: data.rfind(b"\n") + 1]
        text = prefix.decode("utf-8-sig")
        if private_vault_content(text):
            report.status = "private_control"
            return report
        if any(len(line) + 1 > config.max_record_bytes for line in prefix.split(b"\n")[:-1]):
            report.status = "record_too_large"
            return report
        rows = []
        for line in text.split("\n"):
            if line.strip():
                if private_vault_content(line):
                    report.status = "private_control"
                    return report
                row = json.loads(line)
                if isinstance(row, dict) and row.get("format") in {
                    "mnemion-memory-journal",
                    "mnemion-memory-journal-catalog",
                }:
                    report.status = "private_control"
                    return report
                rows.append(row)
        outcomes = []
        parse(
            json.dumps(rows, ensure_ascii=False), relative, messages_only=True, selection=outcomes
        )
        lines = prefix.count(b"\n")
        if config.capture_mode == "complete":
            outcomes = ["selected"] * lines
        else:
            outcomes.extend(["omitted"] * (lines - len(outcomes)))
        counts = SelectionCounts(
            lines=len(outcomes),
            selected=outcomes.count("selected"),
            omitted=outcomes.count("omitted"),
            unsupported=outcomes.count("unsupported"),
        )
        report.status, report.prefix_bytes, report.records = "sampled", len(prefix), counts
    except (OSError, SourceReadError):
        report.status = "unreadable"
    except (UnicodeError, ValueError, RecursionError):
        report.status = "invalid_jsonl"
    return report


def preview(root, value, private_roots=()):
    selection = normalize(root, PreviewSelection.model_validate(value), private_roots)
    config = ConversationConfig(
        path=selection.path,
        scope_id="preview",
        name="Capture preview",
        members=[],
        publish_to_mapped_members=True,
        capture_mode=selection.capture_mode,
        capture_policy=selection.capture_policy,
    )
    result = CapturePreview(
        configuration_hash=selection.fingerprint,
        policy_revision=selection.capture_policy.revision if selection.capture_policy else None,
        observed_at=utc_now(),
        capture_mode=selection.capture_mode,
        catalog="complete",
        visited_entries=0,
        read_bytes=0,
        files=[],
        records=SelectionCounts(),
    )
    deadline, pending = time.monotonic() + MAX_SECONDS, [Path(selection.path)]
    # Scandir is streamed: even an enormous single directory cannot allocate an
    # unbounded catalog. Selection rules match collection; this is only a sample.
    try:
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    if (
                        result.visited_entries >= MAX_ENTRIES
                        or len(result.files) >= min(MAX_FILES, selection.max_files)
                        or result.read_bytes >= MAX_BYTES
                        or time.monotonic() >= deadline
                    ):
                        result.catalog = "limited"
                        return result.model_dump(mode="json")
                    result.visited_entries += 1
                    relative = Path(entry.path).relative_to(selection.path).as_posix()
                    if entry.is_symlink() or Path(entry.path).is_junction():
                        result.catalog = "unavailable"
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if len(Path(relative).parts) > 32:
                            result.catalog = "limited"
                        elif not any(
                            fnmatch.fnmatchcase(relative + "/", rule) for rule in config.exclude
                        ):
                            pending.append(Path(entry.path))
                    elif (
                        entry.is_file(follow_symlinks=False)
                        and relative.lower().endswith(".jsonl")
                        and selected(config, relative)
                    ):
                        report = _sample(
                            config, relative, min(FILE_BYTES, MAX_BYTES - result.read_bytes)
                        )
                        result.files.append(report)
                        result.read_bytes += report.read_bytes
                        result.records = SelectionCounts.model_validate(
                            {
                                key: value + getattr(report.records, key)
                                for key, value in result.records.model_dump().items()
                            }
                        )
    except OSError:
        result.catalog = "unavailable"
    return result.model_dump(mode="json")
