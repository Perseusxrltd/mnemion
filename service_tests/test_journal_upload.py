"""Real PostgreSQL recovery under interrupted transfers and changing authority."""

import base64
import hashlib
import io
from uuid import UUID, uuid4

import psycopg
import pytest

from mnemion.journal.format import JournalCatalog
from mnemion.service.errors import ServiceError
from mnemion.service.journal_upload import JournalUploadService, transport_digest
from mnemion.service.journal_upload_models import (
    CHUNK_BYTES,
    JournalUploadAdvance,
    JournalUploadChunk,
    JournalUploadInput,
)
from mnemion.service.models import RevisionInput
from service_tests.test_journal_recovery import command, entry, next_entry, restore
from mnemion.service.journal_recovery import JournalRecoveryService
from service_tests.test_writeback import identity
from service_tests.test_clients import running
from mnemion import agent_control
from mnemion.sdk import Client
from mnemion.service.api import create_app


def start(service, env, *entries, key=None, **options):
    archived = options.pop("archived", False)
    withdrawn = options.pop("withdrawn", ())
    files = {}
    for item in entries:
        path = ("_archive/" if archived else "") + item.relative_path
        files[path] = files.get(path, b"") + item.line()
    catalog = JournalCatalog(
        tenant_id=entries[0].tenant_id,
        space_id=entries[0].space_id,
        records=len({item.id for item in entries}),
    )
    request = JournalUploadInput(
        catalog=catalog.encoded().decode(),
        files=[{"path": path, "bytes": len(data)} for path, data in files.items()],
        withdrawn_ids=list(withdrawn),
        **options,
    )
    result = service.begin(env.owner, env.space, request, key or str(uuid4()))
    return result, files, request


def chunk(data, offset=0):
    return JournalUploadChunk(
        offset=offset, sha256=hashlib.sha256(data).hexdigest(), data=base64.b64encode(data).decode()
    )


def send(service, env, status, files):
    for file in service.files(env.owner, env.space, UUID(status["id"]))["items"]:
        data = files[file["path"]]
        for offset in range(file["received"], len(data), CHUNK_BYTES):
            status = service.chunk(
                env.owner,
                env.space,
                UUID(status["id"]),
                file["index"],
                chunk(data[offset : offset + CHUNK_BYTES], offset),
            )["upload"]
    return status


def advance(service, env, status, action, **fields):
    return service.advance(
        env.owner,
        env.space,
        UUID(status["id"]),
        JournalUploadAdvance(expected_version=status["version"], action=action, **fields),
    )


def review(service, env, status):
    status = advance(service, env, status, "finish_upload")
    while status["state"] == "reviewing":
        status = advance(service, env, status, "review")
    return status


def approve(service, env, status):
    return advance(
        service,
        env,
        status,
        "authorize",
        preview_sha256=status["preview_sha256"],
        reviewed_complete_inventory=True,
        reviewed_withdrawals=True,
        acknowledge_source_only=True,
        acknowledge_resumable_batches=True,
    )


def test_large_upload_survives_restart_and_applies_all_negatives_first(env):
    service = JournalUploadService(env.memory)
    positive = [
        entry(memory_id=UUID(int=index + 1), text="PostgreSQL mémoire 🌌 " + "evidence " * 140)
        for index in range(1030)
    ]
    original = entry(memory_id=UUID(int=2000))
    restore(JournalRecoveryService(env.memory), env, command(original))
    denial = next_entry(original, action="forget", ts="2026-10-02T10:20:30Z")
    resurrection = next_entry(denial, text="Must not return", subject="Denied")
    absent = uuid4()
    status, files, request = start(
        service, env, *positive, original, denial, resurrection, original, withdrawn=[absent]
    )
    assert status["bytes"] > 1024**2
    first = service.files(env.owner, env.space, UUID(status["id"]))["items"][0]
    data = files[first["path"]][:CHUNK_BYTES]
    accepted = service.chunk(env.owner, env.space, UUID(status["id"]), first["index"], chunk(data))
    assert accepted["file"]["transport_sha256"] == transport_digest("0" * 64, 0, data)
    assert len(data) == CHUNK_BYTES and not accepted["file"]["complete"]
    # A fresh service object needs no original process or in-memory upload buffer.
    service = JournalUploadService(env.memory)
    repeated = service.chunk(env.owner, env.space, UUID(status["id"]), first["index"], chunk(data))
    assert repeated["repeated"] and repeated["upload"] == accepted["upload"]
    with pytest.raises(ServiceError, match="bytes differ"):
        service.chunk(
            env.owner, env.space, UUID(status["id"]), first["index"], chunk(b"x" + data[1:])
        )
    status = send(service, env, accepted["upload"], files)
    assert status["records"] == 1033 and status["duplicates"] == 1
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.memories WHERE space_id=%s", (env.space,)
            ).fetchone()["n"]
            == 1
        )
    status = review(service, env, status)
    assert status["counts"] == {"create": 1030, "withdraw": 1, "deny": 1}
    assert status["reviewed_identities"] == 1032
    assert status["can_restore"]
    status = approve(service, env, status)
    before = status
    status = advance(service, env, status, "restore")
    assert status["applied_counts"] == {"withdraw": 1, "deny": 1}
    with pytest.raises(ServiceError):
        env.memory.fetch(env.owner, original.memory_id)
    with pytest.raises(ServiceError, match="Progress changed"):
        advance(service, env, before, "restore")
    assert service.get(env.owner, env.space, UUID(status["id"])) == status
    while status["state"] == "restoring":
        status = advance(service, env, status, "restore")
    assert (
        status["state"] == "completed" and status["applied_batches"] == status["reviewed_batches"]
    )
    assert env.memory.fetch(env.owner, positive[-1].memory_id)["content"] == positive[-1].text
    with env.db.transaction(env.owner) as conn:
        assert conn.execute(
            "SELECT 1 FROM mnemion.recovery_denials WHERE memory_id=%s", (absent,)
        ).fetchone()
    pages, cursor = [], 0
    while cursor is not None:
        page = service.decisions(env.owner, env.space, UUID(status["id"]), cursor)
        assert len(page["items"]) <= 128
        pages.extend(page["items"])
        cursor = page["next_cursor"]
    assert len(pages) == 1032


def test_changed_destination_requires_new_review_and_preserves_prior_batches(env):
    service = JournalUploadService(env.memory)
    entries = [entry(memory_id=UUID(int=i + 1)) for i in range(70)]
    restore(JournalRecoveryService(env.memory), env, command(entries[-1]))
    newer = next_entry(entries[-1], text="Source correction")
    status, files, _ = start(service, env, *entries, newer)
    status = approve(service, env, review(service, env, send(service, env, status, files)))
    status = advance(service, env, status, "restore")
    assert status["processed_identities"] == 64 and status["state"] == "restoring"
    env.memory.revise(
        env.owner,
        entries[-1].memory_id,
        RevisionInput(
            content="Keep my local correction", expected_version=1, reason="Human decision"
        ),
        "local-review",
    )
    with pytest.raises(ServiceError, match="destination changed"):
        advance(service, env, status, "restore")
    status = advance(service, env, status, "restart_review")
    while status["state"] == "reviewing":
        status = advance(service, env, status, "review")
    assert status["counts"] == {"already_restored": 64, "create": 5, "preserved_changes": 1}
    status = approve(service, env, status)
    while status["state"] == "restoring":
        status = advance(service, env, status, "restore")
    assert (
        env.memory.fetch(env.owner, entries[-1].memory_id)["content"] == "Keep my local correction"
    )
    assert advance(service, env, status, "cancel")["state"] == "cancelled"
    assert env.memory.fetch(env.owner, entries[0].memory_id)["content"] == entries[0].text


@pytest.mark.parametrize("failure", ["missing", "truncated", "version", "path"])
def test_incomplete_or_conflicting_inventory_never_restores(env, failure):
    service = JournalUploadService(env.memory)
    first = entry()
    entries = [first, entry()] if failure == "missing" else [first]
    if failure == "version":
        entries.append(entry(memory_id=first.memory_id))
    status, files, request = start(service, env, *entries)
    path = next(iter(files))
    if failure == "missing":
        files[path] = first.line() + b" " * (len(files[path]) - len(first.line()) - 1) + b"\n"
    elif failure == "truncated":
        files[path] = files[path][:-1] + b" "
    elif failure == "path":
        files[path] = files[path].replace(str(first.writer).encode(), str(uuid4()).encode())
    with pytest.raises(ServiceError):
        send(service, env, status, files)
    current = service.get(env.owner, env.space, UUID(status["id"]))
    assert current["received"] == current["records"] == 0
    with pytest.raises(ServiceError, match="every declared file"):
        advance(service, env, current, "finish_upload")
    assert not env.memory.list(env.owner, env.space)["items"]


def test_private_authority_quota_and_bounded_expiry(env):
    service = JournalUploadService(env.memory)
    status, files, request = start(service, env, entry(), key="same-upload")
    assert service.begin(env.owner, env.space, request, "same-upload") == status
    other, _, _ = start(service, env, entry())
    with pytest.raises(ServiceError, match="two active uploads"):
        start(service, env, entry())
    contributor = identity(env, "contributor")
    with pytest.raises(ServiceError):
        service.get(contributor, env.space, UUID(status["id"]))
    with env.db.transaction(contributor) as conn:
        assert not conn.execute("SELECT 1 FROM mnemion.journal_uploads").fetchone()
    # Only the uploader can read progress even if another principal later gets
    # administrator access. No current private-space authorization means no writes.
    with pytest.raises(ServiceError):
        send(service, env, status, files)
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "DELETE FROM mnemion.space_grants WHERE tenant_id=%s AND principal_id=%s",
            (env.owner.tenant_id, contributor.principal_id),
        )
    status = send(service, env, status, files)
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.journal_uploads SET expires_at='1999-01-01T00:00:00Z' WHERE id=%s",
            (UUID(status["id"]),),
        )
    with pytest.raises(ServiceError) as expired:
        service.get(env.owner, env.space, UUID(status["id"]))
    assert expired.value.status == 410
    with env.worker_db.pool.connection() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT line FROM mnemion.journal_upload_latest")
        conn.rollback()
        assert conn.execute("SELECT mnemion.expire_journal_upload() AS n").fetchone()["n"] > 0
        assert conn.execute("SELECT mnemion.expire_journal_upload() AS n").fetchone()["n"] == 1
    assert len(service.list(env.owner, env.space)["items"]) == 1


def test_late_archived_quarantine_and_release_keep_original_identity(env):
    service = JournalUploadService(env.memory)
    first = entry()
    held = next_entry(first, action="quarantine")
    status, files, _ = start(service, env, first, held, archived=True)
    status = approve(service, env, review(service, env, send(service, env, status, files)))
    status = advance(service, env, status, "restore")
    assert status["applied_counts"] == {"hold": 1}
    with pytest.raises(ServiceError):
        env.memory.fetch(env.owner, first.memory_id)
    released = next_entry(held, text="Reviewed PostgreSQL release")
    status, files, _ = start(service, env, first, held, released, archived=True)
    status = approve(service, env, review(service, env, send(service, env, status, files)))
    assert advance(service, env, status, "restore")["applied_counts"] == {"release": 1}
    assert env.memory.fetch(env.owner, first.memory_id)["content"] == released.text


def test_http_sdk_resume_compares_bytes_and_private_agent_uses_the_same_routes(env):
    app = create_app(env.db, env.embedder, mcp_enabled=False, studio_enabled=False)
    first = entry(text="PostgreSQL evidence " * 3000)
    entries = [first]
    for _ in range(5):
        entries.append(next_entry(entries[-1]))
    entries.append(next_entry(entries[-1], action="quarantine"))
    catalog = JournalCatalog(
        tenant_id=first.tenant_id, space_id=first.space_id, records=len(entries)
    )
    data = b"".join(item.line() for item in entries)
    request = JournalUploadInput(
        catalog=catalog.encoded().decode(),
        files=[{"path": first.relative_path, "bytes": len(data)}],
        withdrawn_ids=[],
    )
    space = str(env.space)
    with running(app) as url, Client(url, env.token) as client:
        status = client.begin_journal_upload(space, request, idempotency_key="sdk-upload")
        upload = str(status.id)
        # Pause after the first accepted chunk, then reopen a fresh stream.
        seen = []
        partial = client.upload_journal_file(
            space, upload, 0, io.BytesIO(data), progress=seen.append, cancelled=lambda: bool(seen)
        )
        assert partial.received > 0
        with pytest.raises(ValueError, match="acknowledged prefix"):
            client.upload_journal_file(space, upload, 0, io.BytesIO(b"X" + data[1:]))
        status = client.upload_journal_file(space, upload, 0, io.BytesIO(data))
        assert status.completed_files == 1
        for action in ("finish_upload", "review"):
            status = client.advance_journal_upload(
                space, upload, JournalUploadAdvance(expected_version=status.version, action=action)
            )
        assert status.can_restore and status.counts == {"hold": 1}
        assert len(client.list_journal_uploads(space).items) == 1
        assert client.journal_upload_decisions(space, upload).items[0].action == "hold"
        result = agent_control.execute(
            client,
            "memory.journal.upload.status",
            {"parameters": {"space_id": space, "upload_id": upload}},
        )
        assert result["result"]["state"] == "reviewed"
        for name in ("begin", "chunk"):
            assert agent_control.describe("memory.journal.upload." + name)["sensitive_input"]


def test_cleanup_drains_chunks_before_deleting_their_file(env):
    service = JournalUploadService(env.memory)
    status, _, _ = start(service, env, entry())
    upload = UUID(status["id"])
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.journal_uploads SET expires_at='1999-01-01T00:00:00Z' WHERE id=%s",
            (upload,),
        )
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO mnemion.journal_upload_chunks
                (tenant_id,upload_id,file_index,file_offset,bytes,sha256) VALUES(%s,%s,0,%s,1,%s)""",
                [(env.owner.tenant_id, upload, offset, "0" * 64) for offset in range(1005)],
            )
    with env.worker_db.pool.connection() as conn:
        assert conn.execute("SELECT mnemion.expire_journal_upload() AS n").fetchone()["n"] == 1000
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.journal_upload_chunks WHERE upload_id=%s", (upload,)
            ).fetchone()[0]
            == 5
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.journal_upload_files WHERE upload_id=%s", (upload,)
            ).fetchone()[0]
            == 1
        )
    env.worker.next_journal_cleanup = 0
    assert env.worker.run_once()


def test_multibyte_character_split_between_chunks_and_byte_bounded_review(env):
    service = JournalUploadService(env.memory)
    # Maximum content records force review batches smaller than 64 identities.
    rows = [entry(text="mémoire 🌌 " * 6000) for _ in range(30)]
    status, files, _ = start(service, env, *rows)
    data = next(iter(files.values()))
    assert len(data) > 2 * 1024**2
    status = send(service, env, status, files)
    status = review(service, env, status)
    assert status["reviewed_batches"] > 1
    with env.db.transaction(env.owner) as conn:
        for batch in conn.execute(
            "SELECT items FROM mnemion.journal_upload_batches WHERE upload_id=%s",
            (UUID(status["id"]),),
        ).fetchall():
            assert len(batch["items"]) < 30
