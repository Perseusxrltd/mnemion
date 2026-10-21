"""Portable encrypted inbox evidence, independent of workspace credentials.

An archive restores local custody, not a server grant or a running source. The
enrollment coordinator must separately verify current authority and any device
migration. No producer files, network requests or models are used here.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import struct
from typing import Literal

from pydantic import Field, field_validator

from .. import backup_encryption as encryption, local_state
from ..archives import _rename_exclusive
from ..capture_coverage import CaptureCoverage, PrefixObservation, utc_now, utc_timestamp
from ..capture_identity import canonical_capture_json
from ..private_output import private_output
from ..service.capture_models import CapturePageInput
from ..service.models import Command
from .conversation_inbox import FORMAT, PAGE_BYTES, SCHEMA, Inbox, InboxError, Limits, binding_value

MAGIC = b"MNMCAP1\n"
HEADER_BYTES = 512 * 1024
DATABASE_BYTES = 2 * 1024**3
BLOCK_BYTES = 1024 * 1024
VALUE_BYTES = 8 * 1024**2
MAX_ROWS = 1_000_000
HASH = re.compile(r"[a-f0-9]{64}\Z")
SCOPE = re.compile(r"conversation:[a-f0-9]{64}\Z")


class CaptureArchiveError(ValueError):
    """A bounded diagnostic without archived content or secret values."""


def _cancel(cancelled):
    if cancelled is not None and cancelled():
        raise encryption.EncryptionCancelled("The capture recovery operation was cancelled.")


def _key(value):
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) != 32 or base64.b64encode(decoded).decode() != value:
            raise ValueError()
        return decoded
    except (ValueError, TypeError):
        raise CaptureArchiveError("The archived inbox key could not be verified.") from None


class Manifest(Command):
    format: Literal["mnemion-capture-archive-v1"]
    created_at: str = Field(max_length=32)
    name: str = Field(min_length=1, max_length=200)
    binding: dict
    limits: dict[str, int]
    database_bytes: int = Field(ge=65536, le=DATABASE_BYTES, strict=True)
    database_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    inbox_key: str = Field(max_length=44, repr=False)

    _time = field_validator("created_at")(utc_timestamp)

    @field_validator("binding")
    @classmethod
    def valid_binding(cls, value):
        return binding_value(value)

    @field_validator("inbox_key")
    @classmethod
    def valid_key(cls, value):
        _key(value)
        return value

    @field_validator("limits")
    @classmethod
    def valid_limits(cls, value):
        if set(value) != set(vars(Limits())):
            raise ValueError("Invalid inbox limits")
        Limits(**value)
        return value


def _copy(reader, writer, count, cancelled=None):
    digest = hashlib.sha256()
    while count:
        _cancel(cancelled)
        block = reader.read(min(BLOCK_BYTES, count))
        if not block:
            raise CaptureArchiveError("The capture archive is incomplete.")
        writer.write(block)
        digest.update(block)
        count -= len(block)
    return digest.hexdigest()


def _space(root, needed):
    if shutil.disk_usage(root).free < needed + 64 * 1024**2:
        raise CaptureArchiveError(
            "More free disk space is required to verify this capture archive."
        )


def _schema(connection):
    return connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
    ).fetchall()


@contextmanager
def _database(path, manifest, cancelled):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA cache_size=-2048")
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, VALUE_BYTES)
        connection.set_progress_handler(lambda: bool(cancelled and cancelled()), 10000)
        with sqlite3.connect(":memory:") as expected:
            expected.executescript(SCHEMA)
            if _schema(connection) != _schema(expected):
                raise CaptureArchiveError("The archive uses an unsupported inbox schema.")
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise CaptureArchiveError("The archived inbox database is damaged.")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise CaptureArchiveError("The archived delivery relationships could not be verified.")
        yield Inbox(
            connection,
            path.parent,
            manifest.binding,
            _key(manifest.inbox_key),
            Limits(**manifest.limits),
        )
    except sqlite3.Error:
        _cancel(cancelled)
        raise CaptureArchiveError("The archived inbox database could not be verified.") from None
    finally:
        connection.close()


def _decoded(inbox, encrypted, identity):
    try:
        return json.loads(inbox._open(encrypted, identity))
    except (ValueError, TypeError, RecursionError):
        raise CaptureArchiveError("The archived inbox contains invalid evidence.") from None


def _audit_values(inbox, cancelled=None):
    """Authenticate every retained encrypted value without loading full history."""
    connection = inbox.connection
    for table in (
        "metadata",
        "events",
        "checkpoints",
        "pages",
        "page_events",
        "denials",
        "producer_segments",
        "producer_events",
    ):
        if connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] > MAX_ROWS:
            raise CaptureArchiveError("The capture archive exceeds the supported history limit.")
    owner = False
    for name, encrypted in connection.execute("SELECT name,value FROM metadata"):
        _cancel(cancelled)
        if name == "owner":
            owner = inbox._open(encrypted, name) == FORMAT.encode()
        elif name == "fence_scan":
            cursor = _decoded(inbox, encrypted, name)
            if cursor is not None and (not isinstance(cursor, str) or not HASH.fullmatch(cursor)):
                raise CaptureArchiveError("The archived deletion position is invalid.")
        elif name == "coverage-summary":
            CaptureCoverage.model_validate(_decoded(inbox, encrypted, "observation:" + name))
        elif name.startswith("coverage:") and SCOPE.fullmatch(name[len("coverage:") :]):
            PrefixObservation.model_validate(_decoded(inbox, encrypted, "observation:" + name))
        else:
            raise CaptureArchiveError("The archive contains unsupported inbox metadata.")
    if not owner:
        raise CaptureArchiveError("The archived inbox owner could not be verified.")
    for event_id, scope, lineage, digest, size, payload, state in connection.execute(
        "SELECT event_id,scope,lineage,digest,size,payload,state FROM events"
    ):
        _cancel(cancelled)
        if (
            any(
                not isinstance(value, str) or not HASH.fullmatch(value)
                for value in (event_id, lineage, digest)
            )
            or not isinstance(scope, str)
            or not SCOPE.fullmatch(scope)
            or type(size) is not int
            or not 0 < size <= PAGE_BYTES
            or (payload is not None) != (state == "pending")
        ):
            raise CaptureArchiveError("The archived event identity could not be verified.")
        if payload is not None:
            raw = inbox._open(payload, "event:" + event_id)
            event = json.loads(raw)
            normalized, actual_lineage = inbox._event(event)
            if (
                raw != normalized
                or len(raw) != size
                or hashlib.sha256(raw).hexdigest() != digest
                or actual_lineage != lineage
                or event["event_id"] != event_id
                or event["producer_scope"] != scope
            ):
                raise CaptureArchiveError("The archived event content could not be verified.")
    for scope, payload in connection.execute("SELECT scope,payload FROM checkpoints"):
        _cancel(cancelled)
        if not SCOPE.fullmatch(scope) or not isinstance(
            _decoded(inbox, payload, "checkpoint:" + scope), dict
        ):
            raise CaptureArchiveError("The archived capture position could not be verified.")
    for page_id, digest, payload, receipt, state in connection.execute(
        "SELECT page_id,digest,payload,receipt,state FROM pages"
    ):
        _cancel(cancelled)
        if (payload is not None) != (state == "pending"):
            raise CaptureArchiveError("The archived delivery state could not be verified.")
        if payload is not None:
            raw = inbox._open(payload, "page:" + page_id)
            page = CapturePageInput.model_validate_json(raw)
            if str(page.page_id) != page_id or hashlib.sha256(raw).hexdigest() != digest:
                raise CaptureArchiveError("The archived delivery page could not be verified.")
            # A page has at most 50 events. Damaged relationship rows must not
            # turn verification into an unbounded in-memory history read.
            members = connection.execute(
                "SELECT event_id FROM page_events WHERE page_id=?", (page_id,)
            ).fetchmany(len(page.events) + 1)
            if len(members) != len(page.events) or {row[0] for row in members} != {
                event.event_id for event in page.events
            }:
                raise CaptureArchiveError("The archived delivery membership could not be verified.")
        if receipt is not None:
            value = _decoded(inbox, receipt, "receipt:" + page_id)
            if (
                not isinstance(value, dict)
                or value.get("page_id") != page_id
                or value.get("durable") is not True
            ):
                raise CaptureArchiveError("The archived delivery receipt could not be verified.")
    for scope, start, payload in connection.execute(
        "SELECT scope,start,payload FROM producer_segments"
    ):
        _cancel(cancelled)
        if not isinstance(_decoded(inbox, payload, f"segment:{scope}:{start}"), list):
            raise CaptureArchiveError("The archived producer references could not be verified.")
    for (lineage,) in connection.execute("SELECT lineage FROM denials"):
        if not isinstance(lineage, str) or not HASH.fullmatch(lineage):
            raise CaptureArchiveError("The archived deletion fence could not be verified.")
    return inbox.status()


def _audit(inbox, cancelled=None):
    try:
        return _audit_values(inbox, cancelled)
    except (ValueError, TypeError, KeyError, InboxError, RecursionError):
        raise CaptureArchiveError("The archived inbox evidence could not be verified.") from None


@dataclass(frozen=True)
class RestoredInbox:
    directory: Path
    binding: dict
    status: dict
    archive_sha256: str
    inbox_key: bytes = field(repr=False)


@dataclass(frozen=True)
class OpenedArchive:
    manifest: Manifest = field(repr=False)
    database: Path
    status: dict
    archive_sha256: str

    def public(self):
        return {
            "format": self.manifest.format,
            "created_at": self.manifest.created_at,
            "name": self.manifest.name,
            "binding": self.manifest.binding,
            "database_bytes": self.manifest.database_bytes,
            "archive_sha256": self.archive_sha256,
            "status": self.status,
            "authenticated": True,
            "workspace_credentials_included": False,
            "source_enrolled": False,
        }


@contextmanager
def opened_archive(source, recovery_key, *, staging_root, expected_sha256=None, cancelled=None):
    """Yield verified private evidence; all extracted material is removed on exit."""
    root = local_state.directory(Path(staging_root))
    # Crypto checks its opened file again. This stat is only a disk-space estimate.
    size = Path(source).stat().st_size
    if not 0 < size <= DATABASE_BYTES + HEADER_BYTES + 4096:
        raise CaptureArchiveError("The capture archive exceeds the supported size.")
    _space(root, size * 2)
    with local_state.temporary_directory(prefix="capture-read-", dir=root) as temporary:
        plain, database = temporary / "archive.payload", temporary / "inbox.sqlite3"
        receipt = encryption.decrypt_file(
            source,
            plain,
            recovery_key,
            expected_kind="bundle",
            cancelled=cancelled,
            maximum_plaintext_bytes=DATABASE_BYTES + HEADER_BYTES + len(MAGIC) + 4,
        )
        if expected_sha256 is not None and receipt.encrypted_sha256 != expected_sha256:
            raise CaptureArchiveError("The capture archive changed after its preview.")
        try:
            with plain.open("rb") as stream:
                if stream.read(len(MAGIC)) != MAGIC:
                    raise ValueError()
                size = struct.unpack(">I", stream.read(4))[0]
                if not 1 <= size <= HEADER_BYTES:
                    raise ValueError()
                raw = json.loads(stream.read(size), object_pairs_hook=encryption._unique)
                manifest = Manifest.model_validate(raw)
                if manifest.model_dump(mode="json") != raw:
                    raise ValueError()
                if plain.stat().st_size != len(MAGIC) + 4 + size + manifest.database_bytes:
                    raise ValueError()
                with private_output(database) as output:
                    digest = _copy(stream, output, manifest.database_bytes, cancelled)
                if digest != manifest.database_sha256:
                    raise ValueError()
            with _database(database, manifest, cancelled) as inbox:
                status = _audit(inbox, cancelled)
        except (ValueError, TypeError, KeyError, struct.error, InboxError, RecursionError):
            raise CaptureArchiveError(
                "The capture archive contents could not be verified."
            ) from None
        _cancel(cancelled)
        yield OpenedArchive(manifest, database, status, receipt.encrypted_sha256)


def export_archive(inbox, inbox_key, output, recovery_key, *, staging_root, name, cancelled=None):
    """Snapshot a caller-locked inbox and publish only authenticated ciphertext."""
    if type(inbox_key) is not bytes or len(inbox_key) != 32 or inbox.connection.in_transaction:
        raise CaptureArchiveError("Finish the inbox transaction before creating its backup.")
    root = local_state.directory(Path(staging_root))
    size = inbox._database_bytes()
    if not 65536 <= size <= DATABASE_BYTES:
        raise CaptureArchiveError("The inbox exceeds the supported archive size.")
    _space(root, size * 2)
    _space(Path(output).parent, size)
    with local_state.temporary_directory(prefix="capture-export-", dir=root) as temporary:
        database, plain = temporary / "inbox.sqlite3", temporary / "archive.payload"
        with private_output(database):
            pass
        connection = sqlite3.connect(database)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            inbox.connection.backup(
                connection, pages=256, progress=lambda *args: _cancel(cancelled)
            )
        finally:
            connection.close()
        with database.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest = Manifest(
            format="mnemion-capture-archive-v1",
            created_at=utc_now(),
            name=name,
            binding=inbox.binding,
            limits=vars(inbox.limits),
            database_bytes=database.stat().st_size,
            database_sha256=digest,
            inbox_key=base64.b64encode(inbox_key).decode(),
        )
        with _database(database, manifest, cancelled) as snapshot:
            status = _audit(snapshot, cancelled)
        header = canonical_capture_json(manifest.model_dump(mode="json"))
        if len(header) > HEADER_BYTES:
            raise CaptureArchiveError("The capture selection exceeds the supported archive header.")
        with private_output(plain) as writer, database.open("rb") as reader:
            writer.write(MAGIC + struct.pack(">I", len(header)) + header)
            if _copy(reader, writer, manifest.database_bytes, cancelled) != digest:
                raise CaptureArchiveError("The capture snapshot changed while being archived.")
        sealed = encryption.encrypt_file(
            plain, output, recovery_key, kind="bundle", cancelled=cancelled
        )
        verified = encryption.verify_file(
            output, recovery_key, expected_kind="bundle", cancelled=cancelled
        )
        if replace(sealed, authenticated=True) != verified:
            raise CaptureArchiveError("The published capture archive could not be confirmed.")
        return OpenedArchive(manifest, database, status, verified.encrypted_sha256).public()


def inspect_archive(source, recovery_key, **options):
    with opened_archive(source, recovery_key, **options) as archive:
        return archive.public()


def restore_new_inbox(
    source, recovery_key, destination, *, staging_root, expected_sha256, cancelled=None
):
    """Restore to a NEW private directory; never enroll, activate or overwrite it.

    The caller must protect the returned inbox key before saving enrollment. A
    workspace key is deliberately absent; current authorization is still needed.
    """
    if not isinstance(expected_sha256, str) or not HASH.fullmatch(expected_sha256):
        raise CaptureArchiveError("Inspect this archive before restoring its inbox.")
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise CaptureArchiveError("Restore into a new inbox; existing evidence was retained.")
    with opened_archive(
        source,
        recovery_key,
        staging_root=staging_root,
        expected_sha256=expected_sha256,
        cancelled=cancelled,
    ) as archive:
        _space(destination.parent, archive.manifest.database_bytes)
        with local_state.temporary_directory(
            prefix="capture-restore-", dir=destination.parent
        ) as temporary:
            with (
                archive.database.open("rb") as reader,
                private_output(temporary / "inbox.sqlite3") as writer,
            ):
                if (
                    _copy(reader, writer, archive.manifest.database_bytes, cancelled)
                    != archive.manifest.database_sha256
                ):
                    raise CaptureArchiveError("The capture snapshot changed during restoration.")
            _cancel(cancelled)
            _rename_exclusive(temporary, destination)
            local_state._sync_directory(destination.parent)
        return RestoredInbox(
            destination,
            archive.manifest.binding,
            archive.status,
            archive.archive_sha256,
            _key(archive.manifest.inbox_key),
        )
