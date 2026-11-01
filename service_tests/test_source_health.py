"""A corrupt text file cannot stop unrelated updates or authorize deletions."""

import hashlib
import json
import subprocess
from uuid import UUID, uuid4

import httpx
import pytest

from mnemion.connectors.config import ConnectorConfig
from mnemion.connectors.runner import sync
from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service.connector_models import BindingInput, ConnectorInput
from mnemion.service.connectors import ConnectorService
from mnemion.service.errors import ServiceError
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput
from service_tests.test_clients import running as serve


def patch_selected_reads(monkeypatch, source_files, blocked):
    """Fail selected opens by source name. On Windows the no-follow opener is the boundary."""
    import os
    from pathlib import Path

    if os.name == "nt":
        real = source_files._windows_open_unfollowed

        def guarded(path, relative):
            error = blocked(Path(path).name)
            if error is not None:
                raise error
            return real(path, relative)

        monkeypatch.setattr(source_files, "_windows_open_unfollowed", guarded)
        return
    real_open = source_files.os.open

    def guarded(path, flags, *args, **kwargs):
        error = blocked(os.fsdecode(path))
        if error is not None:
            raise error
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(source_files.os, "supports_dir_fd", {*os.supports_dir_fd, guarded})
    monkeypatch.setattr(source_files.os, "open", guarded)


@pytest.fixture
def text_source(env, tmp_path):
    service = ConnectorService(env.memory)
    people = {}
    for name in ("capture", "reader", "outsider"):
        person = env.identities.create_principal(
            env.owner, PrincipalInput(name=name, kind="application")
        )
        key = env.identities.create_key(env.owner, UUID(person["id"]), KeyInput(name=name))
        people[name] = env.db.authenticate(key["api_key"]), key["api_key"]
    operator = people["capture"][0]
    connection = UUID(
        service.create(
            env.owner,
            ConnectorInput(
                name="Text fixture",
                provider="filesystem",
                access_mode="published",
                principal_id=operator.principal_id,
            ),
        )["id"]
    )
    service.binding(
        env.owner,
        connection,
        BindingInput(
            external_id="employee:reader",
            principal_id=people["reader"][0].principal_id,
        ),
    )
    source = tmp_path / "notes"
    source.mkdir()
    config = ConnectorConfig.model_validate(
        {
            "service_url": "http://127.0.0.1",
            "connector_id": str(connection),
            "service_token": {"env": "UNUSED_INJECTED_FIXTURE"},
            "provider": {
                "type": "filesystem",
                "path": source,
                "scope_id": "fixture",
                "name": "Fixture",
                "members": ["employee:reader"],
                "publish_to_mapped_members": True,
                "max_file_bytes": 1000,
            },
        }
    )
    return service, connection, people, config


@pytest.mark.parametrize(
    "invalid,code",
    [
        (b"# t\nfoo_\xe2\x80 | bar\n", "source_is_not_utf8_text"),
        (b"binary\0text", "source_contains_binary_data"),
        (b"x" * 1001, "source_too_large"),
    ],
)
def test_corrupt_file_keeps_other_updates_and_last_good_data_until_clean_scan(
    env,
    text_source,
    invalid,
    code,
):
    service, connection, people, config = text_source
    root = config.provider.path
    (root / "bad.md").write_text("Postgres last verified source text", encoding="utf-8")
    (root / "removed.md").write_text("Postgres retained until complete inventory", encoding="utf-8")
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
        Client(url, people["reader"][1]) as reader,
    ):
        assert sync(config, client=client)["completed"]
        first = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(first["space_id"])
        (root / "bad.md").write_bytes(invalid)
        (root / "new.md").write_text("Postgres healthy new decision", encoding="utf-8")
        (root / "removed.md").unlink()
        report = sync(config, client=client)
        assert report["changed"] == 1, report
        assert not report["completed"] and report["removed"] == 0
        partial = report["scopes"][0]
        assert partial["incomplete_inventory"] and not partial["checkpoint_committed"]
        assert partial["skipped_documents"] == 1
        assert partial["file_errors"] == [
            {
                "path": "bad.md",
                "error_code": code,
                "path_sha256": hashlib.sha256(b"bad.md").hexdigest(),
            }
        ]
        current = service.scopes(people["capture"][0], connection)["items"][0]
        assert current["access_current"] and current["suspended_at"] is None
        assert current["completed_at"] == first["completed_at"]
        assert current["inventory"]["skipped_documents"] == 1
        assert service.sync_status(env.owner, connection)["last_successful"] is False
        result = reader.request(
            "POST",
            "/v1/recall",
            body={
                "query": "Postgres",
                "mode": "lexical",
                "all_accessible": True,
            },
        )
        assert len(result["hits"]) == 3
        assert "connector_inventory_incomplete" in result["warnings"]
        health = reader.source_health().model_dump()
        assert health["incomplete_scopes"] == health["skipped_documents"] == 1
        assert "connector_inventory_incomplete" in health["attention"]
        assert "bad.md" not in str(health)
        ready = reader.request("GET", "/health/ready")
        assert ready["source_health_checked"]
        assert ready["attention"] == ["connector_inventory_incomplete"]
        public = httpx.get(url + "/health/ready").json()
        assert not public["source_health_checked"] and public["attention"] == []
        assert httpx.get(url + "/v1/health/sources").status_code == 401
        with Client(url, people["outsider"][1]) as outsider:
            assert outsider.request("GET", "/v1/health/sources")["attention"] == []
        with env.db.transaction(people["capture"][0]) as conn:
            before = conn.execute(
                "SELECT id FROM mnemion.memories WHERE space_id=%s AND deleted_at IS NULL",
                (space,),
            ).fetchall()
        (root / "bad.md").write_text("Postgres repaired current source text", encoding="utf-8")
        recovered = sync(config, client=client)
        assert recovered["completed"] and recovered["changed"] == 1
        assert recovered["removed"] == 1
        assert reader.request("GET", "/v1/health/sources")["attention"] == []
        after = reader.request(
            "POST",
            "/v1/recall",
            body={
                "query": "Postgres",
                "mode": "lexical",
                "all_accessible": True,
            },
        )
        assert len(after["hits"]) == 2
        assert "connector_inventory_incomplete" not in after["warnings"]
        visible = 0
        for row in before:
            try:
                env.memory.fetch(people["reader"][0], row["id"])
                visible += 1
            except ServiceError as error:
                assert error.status == 404
        assert visible == 2  # Repair reused the original stable memory identity.


def test_health_explains_unavailable_sources_without_leaking_other_grants(env, text_source):
    service, connection, people, config = text_source
    (config.provider.path / "source.md").write_text("Postgres current evidence", encoding="utf-8")
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
        Client(url, people["reader"][1]) as reader,
        Client(url, people["outsider"][1]) as outsider,
    ):
        assert sync(config, client=client)["completed"]
        scope = service.scopes(people["capture"][0], connection)["items"][0]
        service.suspend(env.owner, UUID(scope["space_id"]), "operator_paused")
        health = reader.request("GET", "/v1/health/sources")
        assert health["unavailable_scopes"] == 1
        assert health["attention"] == ["connector_scope_suspended"]
        assert scope["space_id"] not in json.dumps(health)
        assert outsider.request("GET", "/v1/health/sources")["attention"] == []
        recall = reader.request(
            "POST",
            "/v1/recall",
            body={
                "query": "Postgres",
                "mode": "lexical",
                "all_accessible": True,
            },
        )
        assert recall["hits"] == [] and "connector_scope_suspended" in recall["warnings"]
        env.identities.grant(
            env.owner, env.space, people["reader"][0].principal_id, GrantInput(role="reader")
        )
        narrowed = reader.request(
            "POST",
            "/v1/recall",
            body={
                "query": "Postgres",
                "mode": "lexical",
                "space_ids": [str(env.space)],
            },
        )
        assert "connector_scope_suspended" not in narrowed["warnings"]
        service.resume(env.owner, UUID(scope["space_id"]))
        service.binding(
            env.owner,
            connection,
            BindingInput(
                external_id="employee:reader",
                principal_id=people["reader"][0].principal_id,
            ),
            remove=True,
        )
        assert sync(config, client=client)["completed"]
        assert reader.request("GET", "/v1/health/sources")["attention"] == []


def test_file_diagnostics_are_bounded_and_do_not_acknowledge_a_requested_sync(env, text_source):
    service, connection, people, config = text_source
    root = config.provider.path
    for number in range(60):
        (root / f"bad-{number:02}.md").write_bytes(b"\xff")
    (root / "valid.md").write_text("Postgres valid evidence", encoding="utf-8")
    from mnemion.service.connector_models import SyncRequestInput

    service.request_sync(env.owner, connection, SyncRequestInput(expected_generation=0))
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
    ):
        report = sync(config, client=client)
        assert report["changed"] == 1 and not report["completed"]
        assert report["scopes"][0]["skipped_documents"] == 60
        assert len(report["scopes"][0]["file_errors"]) == 50
        assert service.sync_status(env.owner, connection)["pending"]
        for path in root.glob("bad-*.md"):
            path.unlink()
        assert sync(config, client=client)["completed"]
        assert not service.sync_status(env.owner, connection)["pending"]


def test_unreadable_journal_catalog_still_closes_the_scope(env, text_source):
    service, connection, people, config = text_source
    root = config.provider.path
    (root / "note.md").write_text("Postgres current evidence", encoding="utf-8")
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
    ):
        assert sync(config, client=client)["completed"]
        (root / "catalog.json").write_bytes(b"\xff")
        report = sync(config, client=client)
        assert not report["completed"]
        assert report["scopes"][0]["error_code"] == "journal_inventory_unreadable"
        assert report["scopes"][0]["access_suspended"]


def test_older_server_keeps_fail_closed_behavior_with_upgrade_hint(env, text_source):
    _, _, people, config = text_source
    (config.provider.path / "bad.md").write_bytes(b"\xff")
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
    ):
        original = client.request

        def older(method, path, **kwargs):
            if path == "/health/live":
                return {"status": "alive", "api_version": "v1", "service_version": "4.20.0"}
            return original(method, path, **kwargs)

        client.request = older
        report = sync(config, client=client)
        assert report["scopes"][0]["error_code"] == "text_source_server_upgrade_required"
        assert report["scopes"][0]["access_suspended"]


def test_git_pinned_inventory_isolates_content_errors_without_rewriting_sources(tmp_path):
    from mnemion.connectors.config import GitConfig
    from mnemion.connectors.protocol import Document, SkippedDocument
    from mnemion.connectors.providers import GitProvider

    root = tmp_path / "repository"
    root.mkdir()
    files = {
        "bad.md": b"\xff",
        "binary.md": b"a\0b",
        "large.md": b"x" * 1001,
        "healthy.md": b"Postgres healthy evidence",
    }
    for name, data in files.items():
        (root / name).write_bytes(data)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)], check=True, capture_output=True
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Source fixture",
        ],
        check=True,
        capture_output=True,
    )
    adapter = GitProvider(
        GitConfig(
            type="git",
            path=root,
            name="Fixture",
            scope_id="fixture",
            members=[],
            publish_to_mapped_members=True,
            max_file_bytes=1000,
        )
    )
    results = list(adapter.documents(adapter.scopes()[0]))
    assert [value.external_id for value in results if isinstance(value, Document)] == ["healthy.md"]
    assert {value.path: value.code for value in results if isinstance(value, SkippedDocument)} == {
        "bad.md": "source_is_not_utf8_text",
        "binary.md": "source_contains_binary_data",
        "large.md": "source_too_large",
    }
    assert {name: (root / name).read_bytes() for name in files} == files


def test_partial_diagnostics_cannot_change_a_deletion_sweep_in_progress(text_source):
    from mnemion.service.connector_models import BatchInput, FinishInput, ScopeInput, utc_now
    from service_tests.test_connectors import begin, item

    service, connection, people, _ = text_source
    operator = people["capture"][0]
    space = UUID(
        service.refresh_scope(
            operator,
            connection,
            ScopeInput(
                external_id="large-fixture",
                name="Fixture",
                members=["employee:reader"],
                observed_at=utc_now(),
            ),
        )["space_id"]
    )
    run = begin(service, operator, space)
    for sequence, start in enumerate(range(0, 101, 50)):
        service.page(
            operator,
            space,
            run,
            BatchInput(
                sequence=sequence,
                items=[item(f"document-{index}") for index in range(start, min(101, start + 50))],
            ),
        )
    service.finish(operator, space, run, FinishInput(complete_inventory=True))
    sweep = begin(service, operator, space)
    service.page(operator, space, sweep, BatchInput(sequence=0, items=[]))
    first = service.finish(operator, space, sweep, FinishInput(complete_inventory=True))
    assert first["state"] == "finalizing" and first["removed"] == 100
    with pytest.raises(ServiceError) as refused:
        service.finish(
            operator,
            space,
            sweep,
            FinishInput(
                skipped_documents=1,
                file_errors=[
                    {
                        "path": "bad.md",
                        "path_sha256": hashlib.sha256(b"bad.md").hexdigest(),
                        "error_code": "source_is_not_utf8_text",
                    }
                ],
            ),
        )
    assert refused.value.code == "inventory_already_finalizing"
    final = service.finish(operator, space, sweep, FinishInput(complete_inventory=True))
    assert final["removed"] == 101 and final["checkpoint_committed"]


def test_unreadable_selected_file_is_actionable_and_does_not_certify_deletion(
    env, text_source, monkeypatch
):
    import errno

    from mnemion.connectors import source_files
    from mnemion.service.connector_models import ScopeInput, utc_now

    service, connection, people, config = text_source
    root = config.provider.path
    (root / "a-kept.md").write_text("Postgres kept before denial", encoding="utf-8")
    (root / "gone.md").write_text("Postgres retained until access scan", encoding="utf-8")

    def blocked(name):
        if name == "denied.md":
            return PermissionError(errno.EACCES, "PRIVATE_OS_STRING", str(root / "denied.md"))
        return None

    patch_selected_reads(monkeypatch, source_files, blocked)
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
        Client(url, people["reader"][1]) as reader,
    ):
        assert sync(config, client=client)["completed"]
        first = service.scopes(people["capture"][0], connection)["items"][0]
        indexed = reader.request(
            "POST",
            "/v1/recall",
            body={"query": "Postgres", "mode": "lexical", "all_accessible": True},
        )
        gone_hits = [hit for hit in indexed["hits"] if "retained until access scan" in hit["text"]]
        assert gone_hits
        gone_memory = UUID(gone_hits[0]["memory_id"])
        (root / "gone.md").unlink()
        (root / "denied.md").write_text("Postgres denied body", encoding="utf-8")
        (root / "later.md").write_text("Postgres later must stay unread", encoding="utf-8")
        report = sync(config, client=client)
        assert not report["completed"] and report["removed"] == 0 and report["changed"] == 0
        scope = report["scopes"][0]
        assert scope["error_code"] == "source_permission_denied"
        assert scope["access_suspended"] and scope["incomplete_inventory"]
        assert scope["checkpoint_committed"] is False
        assert scope["file_errors"] == [
            {
                "path": "denied.md",
                "error_code": "source_permission_denied",
                "path_sha256": hashlib.sha256(b"denied.md").hexdigest(),
            }
        ]
        assert "PRIVATE_OS_STRING" not in json.dumps(report)
        assert str(root) not in json.dumps(report)
        current = service.scopes(people["capture"][0], connection)["items"][0]
        assert current["completed_at"] == first["completed_at"]
        assert current["inventory"]["file_errors"][0]["path"] == "denied.md"
        assert service.sync_status(env.owner, connection)["last_successful"] is False
        diagnosis = service.health(env.owner, details=True)
        item = diagnosis["diagnostics"]["items"][0]
        assert item["recovery"] == "repair_source_files"
        assert "inventory_incomplete" in item["reasons"]
        assert "provider_unavailable" in item["reasons"]
        assert "denied.md" not in json.dumps(diagnosis)
        assert "PRIVATE_OS_STRING" not in json.dumps(diagnosis)
        hidden = reader.request(
            "POST",
            "/v1/recall",
            body={"query": "Postgres", "mode": "lexical", "all_accessible": True},
        )
        assert hidden["hits"] == [] and "connector_scope_suspended" in hidden["warnings"]
        service.refresh_scope(
            people["capture"][0],
            connection,
            ScopeInput(
                external_id=current["external_id"],
                name="Fixture",
                members=["employee:reader"],
                observed_at=utc_now(),
            ),
        )
        refreshed = service.scopes(people["capture"][0], connection)["items"][0]
        assert refreshed["suspended_at"] is None and refreshed["access_current"]
        assert refreshed["completed_at"] == first["completed_at"]
        assert refreshed["inventory"]["file_errors"][0]["error_code"] == "source_permission_denied"
        health = reader.source_health().model_dump()
        assert health["unavailable_scopes"] == 0
        assert health["incomplete_scopes"] == health["skipped_documents"] == 1
        assert health["attention"] == ["connector_inventory_incomplete"]
        assert "denied.md" not in str(health)
        still = reader.request(
            "POST",
            "/v1/recall",
            body={"query": "Postgres", "mode": "lexical", "all_accessible": True},
        )
        visible = " ".join(hit["text"] for hit in still["hits"])
        assert "kept before denial" in visible
        assert "retained until access scan" not in visible
        assert "later must stay unread" not in visible
        assert "denied body" not in visible
        assert "connector_inventory_incomplete" in still["warnings"]
        assert env.memory.fetch(people["capture"][0], gone_memory)["content"].startswith(
            "Postgres retained"
        )
        with pytest.raises(ServiceError) as hidden_gone:
            env.memory.fetch(people["reader"][0], gone_memory)
        assert hidden_gone.value.status == 404


def test_previously_indexed_denial_stays_hidden_after_root_refresh(env, text_source, monkeypatch):
    """Indexed files stay hidden after denial until a later scan reads them again."""
    import errno

    from mnemion.connectors import source_files
    from mnemion.service.connector_models import (
        BatchInput,
        ConnectorItemInput,
        RunInput,
        ScopeInput,
        utc_now,
    )

    service, connection, people, config = text_source
    root = config.provider.path
    (root / "a-kept.md").write_text("Postgres kept beside denial", encoding="utf-8")
    (root / "m-denied.md").write_text("Postgres indexed before denial", encoding="utf-8")
    (root / "z-second.md").write_text("Postgres second denial unread", encoding="utf-8")
    env.identities.grant(
        env.owner,
        env.space,
        people["reader"][0].principal_id,
        GrantInput(role="reader"),
    )
    native = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Postgres native neighbor stays"),
        "field47-native-neighbor",
    )
    native_id = UUID(native["memory_id"])
    deny = {"on": False}
    denied_names = {"m-denied.md", "z-second.md"}

    def blocked(name):
        if deny["on"] and name in denied_names:
            return PermissionError(errno.EACCES, "PRIVATE_OS_STRING", str(root / "m-denied.md"))
        return None

    def recall(reader):
        return reader.request(
            "POST",
            "/v1/recall",
            body={"query": "Postgres", "mode": "lexical", "all_accessible": True},
        )

    def items(space):
        with env.db.transaction(people["capture"][0]) as conn:
            rows = conn.execute(
                """SELECT external_id, origin_revision, state, withheld_at, validated_run, memory_id
                   FROM mnemion.connector_items WHERE space_id=%s""",
                (space,),
            ).fetchall()
        return {row["memory_id"]: row for row in rows}

    def refresh(external_id):
        service.refresh_scope(
            people["capture"][0],
            connection,
            ScopeInput(
                external_id=external_id,
                name="Fixture",
                members=["employee:reader"],
                observed_at=utc_now(),
            ),
        )

    patch_selected_reads(monkeypatch, source_files, blocked)
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
        Client(url, people["reader"][1]) as reader,
    ):
        assert sync(config, client=client)["completed"]
        first = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(first["space_id"])
        indexed = recall(reader)
        denied_memory = UUID(
            next(
                hit["memory_id"]
                for hit in indexed["hits"]
                if "indexed before denial" in hit["text"]
            )
        )
        second_memory = UUID(
            next(
                hit["memory_id"] for hit in indexed["hits"] if "second denial unread" in hit["text"]
            )
        )
        kept_memory = UUID(
            next(hit["memory_id"] for hit in indexed["hits"] if "kept beside denial" in hit["text"])
        )
        assert env.memory.fetch(people["reader"][0], denied_memory)["content"].startswith(
            "Postgres indexed"
        )
        assert env.memory.fetch(people["reader"][0], native_id)["content"].startswith(
            "Postgres native"
        )
        deny["on"] = True
        report = sync(config, client=client)
        assert not report["completed"] and report["removed"] == 0 and report["changed"] == 0
        scope = report["scopes"][0]
        assert scope["error_code"] == "source_permission_denied"
        assert scope["incomplete_inventory"] and scope["checkpoint_committed"] is False
        assert [error["path"] for error in scope["file_errors"]] == ["m-denied.md"]
        assert "z-second.md" not in json.dumps(scope["file_errors"])
        assert "PRIVATE_OS_STRING" not in json.dumps(report)
        held = items(space)
        assert held[kept_memory]["withheld_at"] is None
        assert held[denied_memory]["withheld_at"] is not None
        assert held[second_memory]["withheld_at"] is not None
        assert held[denied_memory]["validated_run"] == held[second_memory]["validated_run"]
        assert held[kept_memory]["validated_run"] != held[denied_memory]["validated_run"]
        assert all(row["state"] != "deleted" for row in held.values())
        refresh(first["external_id"])
        refreshed = service.scopes(people["capture"][0], connection)["items"][0]
        assert refreshed["suspended_at"] is None and refreshed["access_current"]
        assert refreshed["completed_at"] == first["completed_at"]
        assert refreshed["inventory"]["file_errors"][0]["path"] == "m-denied.md"
        visible = " ".join(hit["text"] for hit in recall(reader)["hits"])
        assert "kept beside denial" in visible
        assert "native neighbor stays" in visible
        assert "indexed before denial" not in visible
        assert "second denial unread" not in visible
        for memory_id in (denied_memory, second_memory):
            with pytest.raises(ServiceError) as missing:
                env.memory.fetch(people["reader"][0], memory_id)
            assert missing.value.status == 404
        assert env.memory.fetch(people["reader"][0], kept_memory)["content"].startswith(
            "Postgres kept"
        )
        target = held[denied_memory]
        retain_run = uuid4()
        service.begin(people["capture"][0], space, RunInput(run_id=retain_run))
        retained = service.page(
            people["capture"][0],
            space,
            retain_run,
            BatchInput(
                sequence=0,
                items=[
                    ConnectorItemInput(
                        external_id=target["external_id"],
                        revision=target["origin_revision"],
                        action="retain",
                    )
                ],
            ),
        )
        assert retained["items"][0]["outcome"] == "unchanged"
        after_retain = items(space)
        assert after_retain[denied_memory]["withheld_at"] is not None
        assert after_retain[denied_memory]["validated_run"] == target["validated_run"]
        assert after_retain[second_memory]["withheld_at"] is not None
        service.suspend(people["capture"][0], space, "provider_unavailable")
        refresh(first["external_id"])
        still = items(space)
        assert still[denied_memory]["withheld_at"] is not None
        assert still[second_memory]["withheld_at"] is not None
        assert still[kept_memory]["withheld_at"] is None
        visible = " ".join(hit["text"] for hit in recall(reader)["hits"])
        assert "indexed before denial" not in visible and "second denial unread" not in visible
        assert "kept beside denial" in visible and "native neighbor stays" in visible
        deny["on"] = False
        repaired = sync(config, client=client)
        assert repaired["completed"] and repaired["removed"] == 0 and repaired["changed"] == 0
        restored = recall(reader)
        texts = " ".join(hit["text"] for hit in restored["hits"])
        assert "indexed before denial" in texts and "second denial unread" in texts
        assert "kept beside denial" in texts and "native neighbor stays" in texts
        assert "connector_inventory_incomplete" not in restored["warnings"]
        assert env.memory.fetch(people["reader"][0], denied_memory)["content"].startswith(
            "Postgres indexed"
        )
        assert env.memory.fetch(people["reader"][0], second_memory)["content"].startswith(
            "Postgres second"
        )
        repaired_items = items(space)
        assert repaired_items[denied_memory]["withheld_at"] is None
        assert repaired_items[second_memory]["withheld_at"] is None
        assert repaired_items[denied_memory]["state"] != "deleted"
        assert (
            repaired_items[second_memory]["validated_run"]
            == repaired_items[kept_memory]["validated_run"]
        )


def test_withheld_source_is_not_embedded_after_root_refresh(env, text_source, monkeypatch):
    """A current root lease must not send a held file to the embedder."""
    import errno

    from mnemion.connectors import source_files
    from mnemion.service.connector_models import ScopeInput, utc_now

    service, connection, people, config = text_source
    root = config.provider.path
    (root / "a-kept.md").write_text("Postgres kept beside denial", encoding="utf-8")
    (root / "m-denied.md").write_text("Postgres indexed before denial", encoding="utf-8")
    (root / "z-second.md").write_text("Postgres second denial unread", encoding="utf-8")
    deny = {"on": False}
    denied_names = {"m-denied.md", "z-second.md"}

    def blocked(name):
        if deny["on"] and name in denied_names:
            return PermissionError(errno.EACCES, "PRIVATE_OS_STRING", str(root / "m-denied.md"))
        return None

    def memories(space):
        with env.db.transaction(people["capture"][0]) as conn:
            rows = conn.execute(
                """SELECT m.id, r.content FROM mnemion.memories m
                   JOIN mnemion.memory_revisions r
                     ON r.tenant_id=m.tenant_id AND r.id=m.current_revision_id
                   WHERE m.space_id=%s AND m.deleted_at IS NULL""",
                (space,),
            ).fetchall()
        return {row["content"]: row["id"] for row in rows}

    def lease(space, memory_id):
        with env.worker_db.worker_transaction(env.owner.tenant_id) as conn:
            row = conn.execute(
                """SELECT j.id FROM mnemion.jobs j
                   JOIN mnemion.memory_revisions r
                     ON r.tenant_id=j.tenant_id AND r.id=j.revision_id
                   WHERE j.space_id=%s AND j.kind='embed' AND j.state='pending'
                     AND r.memory_id=%s ORDER BY j.created_at LIMIT 1""",
                (space, memory_id),
            ).fetchone()
            assert row
            return conn.execute(
                """UPDATE mnemion.jobs SET state='leased',lease_id=%s,
                   lease_until=now()+interval '1 minute',attempts=1
                   WHERE id=%s RETURNING *""",
                (uuid4(), row["id"]),
            ).fetchone()

    def embedded(memory_id):
        with env.worker_db.worker_transaction(env.owner.tenant_id) as conn:
            return conn.execute(
                """SELECT count(*) AS n FROM mnemion.embeddings e
                   JOIN mnemion.memory_revisions r
                     ON r.tenant_id=e.tenant_id AND r.id=e.revision_id
                   WHERE r.memory_id=%s""",
                (memory_id,),
            ).fetchone()["n"]

    patch_selected_reads(monkeypatch, source_files, blocked)
    calls = []
    original = env.embedder.document

    def inference(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(env.embedder, "document", inference)
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
    ):
        assert sync(config, client=client)["completed"]
        scope = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(scope["space_id"])
        indexed = memories(space)
        denied_id = indexed["Postgres indexed before denial"]
        second_id = indexed["Postgres second denial unread"]
        kept_id = indexed["Postgres kept beside denial"]
        deny["on"] = True
        denied = sync(config, client=client)
        assert not denied["completed"] and denied["removed"] == 0
        service.refresh_scope(
            people["capture"][0],
            connection,
            ScopeInput(
                external_id=scope["external_id"],
                name="Fixture",
                members=["employee:reader"],
                observed_at=utc_now(),
            ),
        )
        for memory_id in (denied_id, second_id):
            assert env.worker.process(lease(space, memory_id)) is False
            assert embedded(memory_id) == 0
        assert not any(
            "indexed before denial" in text or "second denial unread" in text for text in calls
        )
        assert env.worker.process(lease(space, kept_id)) is True
        assert any("kept beside denial" in text for text in calls)
        assert embedded(kept_id) > 0
        assert embedded(denied_id) == 0 and embedded(second_id) == 0
        deny["on"] = False
        repaired = sync(config, client=client)
        assert repaired["completed"] and repaired["removed"] == 0 and repaired["changed"] == 0
        assert env.worker.process(lease(space, denied_id)) is True
        assert env.worker.process(lease(space, second_id)) is True
        assert any("indexed before denial" in text for text in calls)
        assert any("second denial unread" in text for text in calls)
        assert embedded(denied_id) > 0 and embedded(second_id) > 0


def _recall(reader):
    return reader.request(
        "POST",
        "/v1/recall",
        body={"query": "Postgres", "mode": "lexical", "all_accessible": True},
    )


def _connector_items(env, people, space):
    with env.db.transaction(people["capture"][0]) as conn:
        rows = conn.execute(
            """SELECT external_id, origin_revision, state, withheld_at, validated_run, memory_id
               FROM mnemion.connector_items WHERE space_id=%s""",
            (space,),
        ).fetchall()
    return {row["memory_id"]: row for row in rows}


def _refresh_root(service, people, connection, external_id):
    from mnemion.service.connector_models import ScopeInput, utc_now

    service.refresh_scope(
        people["capture"][0],
        connection,
        ScopeInput(
            external_id=external_id,
            name="Fixture",
            members=["employee:reader"],
            observed_at=utc_now(),
        ),
    )


def _texts(reader):
    return " ".join(hit["text"] for hit in _recall(reader)["hits"])


def _item_for_text(env, people, space, reader, fragment):
    """Original memory id from authorized recall, then the database row for that id."""
    memory_id = UUID(
        next(hit["memory_id"] for hit in _recall(reader)["hits"] if fragment in hit["text"])
    )
    return _connector_items(env, people, space)[memory_id]


def test_unreadable_selected_directory_stays_hidden_after_root_refresh(
    env, text_source, monkeypatch
):
    """Not run on 1 November 2026. A denied child directory is not an empty inventory."""
    import errno
    import os
    from pathlib import Path

    from mnemion.connectors import providers
    from mnemion.service.connector_models import (
        BatchInput,
        ConnectorItemInput,
        RunInput,
        SyncRequestInput,
    )

    service, connection, people, config = text_source
    root = config.provider.path
    (root / "a-kept.md").write_text("Postgres kept beside directory", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / "old.md").write_text("Postgres indexed inside directory", encoding="utf-8")
    (root / "z-later.md").write_text("Postgres later directory unread", encoding="utf-8")
    env.identities.grant(
        env.owner,
        env.space,
        people["reader"][0].principal_id,
        GrantInput(role="reader"),
    )
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Postgres native directory neighbor"),
        "field47-directory-neighbor",
    )
    deny = {"on": False}
    real_scandir = providers.os.scandir

    def scandir(path):
        if deny["on"] and Path(path).name == "nested":
            raise PermissionError(errno.EACCES, "PRIVATE_OS_STRING", os.fspath(path))
        return real_scandir(path)

    monkeypatch.setattr(providers.os, "scandir", scandir)
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
        Client(url, people["reader"][1]) as reader,
    ):
        assert sync(config, client=client)["completed"]
        first = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(first["space_id"])
        old = _item_for_text(env, people, space, reader, "indexed inside directory")
        kept = _item_for_text(env, people, space, reader, "kept beside directory")
        later = _item_for_text(env, people, space, reader, "later directory unread")
        status = service.sync_status(env.owner, connection)
        service.request_sync(
            env.owner,
            connection,
            SyncRequestInput(expected_generation=status["requested_generation"]),
        )
        deny["on"] = True
        report = sync(config, client=client)
        assert not report["completed"] and report["removed"] == 0
        scope = report["scopes"][0]
        assert scope["error_code"] == "source_permission_denied"
        assert scope["incomplete_inventory"] and scope["checkpoint_committed"] is False
        assert scope["file_errors"] == [
            {
                "path": "nested",
                "error_code": "source_permission_denied",
                "path_sha256": hashlib.sha256(b"nested").hexdigest(),
            }
        ]
        rendered = json.dumps(report)
        assert "PRIVATE_OS_STRING" not in rendered and str(root) not in rendered
        assert service.sync_status(env.owner, connection)["pending"]
        assert service.sync_status(env.owner, connection)["last_successful"] is False
        held = _connector_items(env, people, space)
        assert held[kept["memory_id"]]["withheld_at"] is None
        assert held[later["memory_id"]]["withheld_at"] is None
        assert held[old["memory_id"]]["withheld_at"] is not None
        assert all(row["state"] != "deleted" for row in held.values())
        current = service.scopes(people["capture"][0], connection)["items"][0]
        assert current["completed_at"] == first["completed_at"]
        _refresh_root(service, people, connection, first["external_id"])
        refreshed = service.scopes(people["capture"][0], connection)["items"][0]
        assert refreshed["suspended_at"] is None and refreshed["access_current"]
        assert refreshed["inventory"]["file_errors"][0]["path"] == "nested"
        visible = _texts(reader)
        assert "kept beside directory" in visible and "later directory unread" in visible
        assert "native directory neighbor" in visible
        assert "indexed inside directory" not in visible
        retain_run = uuid4()
        service.begin(people["capture"][0], space, RunInput(run_id=retain_run))
        retained = service.page(
            people["capture"][0],
            space,
            retain_run,
            BatchInput(
                sequence=0,
                items=[
                    ConnectorItemInput(
                        external_id=old["external_id"],
                        revision=old["origin_revision"],
                        action="retain",
                    )
                ],
            ),
        )
        assert retained["items"][0]["outcome"] == "unchanged"
        assert _connector_items(env, people, space)[old["memory_id"]]["withheld_at"] is not None
        service.suspend(people["capture"][0], space, "provider_unavailable")
        _refresh_root(service, people, connection, first["external_id"])
        deny["on"] = False
        repaired = sync(config, client=client)
        assert repaired["completed"] and repaired["removed"] == 0
        restored = _connector_items(env, people, space)
        assert restored[old["memory_id"]]["withheld_at"] is None
        assert restored[old["memory_id"]]["state"] != "deleted"
        assert restored[old["memory_id"]]["origin_revision"] == old["origin_revision"]
        assert "indexed inside directory" in _texts(reader)
        with env.db.transaction(people["capture"][0]) as conn:
            failed = conn.execute(
                """SELECT result FROM mnemion.connector_runs
                   WHERE space_id=%s AND state='completed' AND result->>'incomplete_inventory'='true'
                   ORDER BY finished_at, id""",
                (space,),
            ).fetchall()
        assert failed[0]["result"]["file_errors"][0]["path"] == "nested"
        latest = service.scopes(people["capture"][0], connection)["items"][0]
        assert latest["completed_at"] != first["completed_at"]
        assert not latest["inventory"]["incomplete_inventory"]


def test_replaced_directory_link_stays_hidden_until_the_real_tree_returns(
    env, text_source, tmp_path
):
    """Not run on 1 November 2026. Replacing a directory with a link is not a deletion."""
    import shutil

    service, connection, people, config = text_source
    root = config.provider.path
    (root / "a-kept.md").write_text("Postgres kept beside link", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / "old.md").write_text("Postgres indexed behind link", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.md").write_text("Postgres outside link secret", encoding="utf-8")
    env.identities.grant(
        env.owner,
        env.space,
        people["reader"][0].principal_id,
        GrantInput(role="reader"),
    )
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Postgres native link neighbor"),
        "field47-link-neighbor",
    )
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
        Client(url, people["reader"][1]) as reader,
    ):
        assert sync(config, client=client)["completed"]
        first = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(first["space_id"])
        old = _item_for_text(env, people, space, reader, "indexed behind link")
        backup = tmp_path / "nested-real"
        shutil.move(nested, backup)
        try:
            (root / "nested").symlink_to(outside, target_is_directory=True)
        except OSError:
            shutil.move(backup, nested)
            pytest.skip("Creating symlinks requires Windows developer mode or privilege")
        report = sync(config, client=client)
        assert not report["completed"] and report["removed"] == 0
        scope = report["scopes"][0]
        assert scope["error_code"] == "source_symlinks_not_supported"
        assert scope["checkpoint_committed"] is False and scope["incomplete_inventory"]
        assert scope["file_errors"][0]["path"] == "nested"
        assert scope["file_errors"][0]["error_code"] == "source_symlinks_not_supported"
        rendered = json.dumps(report)
        assert str(outside) not in rendered and "outside link secret" not in rendered
        _refresh_root(service, people, connection, first["external_id"])
        visible = _texts(reader)
        assert "kept beside link" in visible and "native link neighbor" in visible
        assert "indexed behind link" not in visible and "outside link secret" not in visible
        assert (
            service.scopes(people["capture"][0], connection)["items"][0]["completed_at"]
            == (first["completed_at"])
        )
        (root / "nested").unlink()
        shutil.move(backup, nested)
        repaired = sync(config, client=client)
        assert repaired["completed"] and repaired["removed"] == 0
        restored = _connector_items(env, people, space)
        assert restored[old["memory_id"]]["withheld_at"] is None
        assert restored[old["memory_id"]]["origin_revision"] == old["origin_revision"]
        assert "indexed behind link" in _texts(reader)
        assert "outside link secret" not in _texts(reader)
        with env.db.transaction(people["capture"][0]) as conn:
            failed = conn.execute(
                """SELECT result->>'incomplete_inventory' AS incomplete,
                          result->'file_errors' AS errors
                   FROM mnemion.connector_runs
                   WHERE space_id=%s AND state='completed'
                   ORDER BY finished_at, id""",
                (space,),
            ).fetchall()
        assert any(
            row["incomplete"] == "true" and row["errors"][0]["path"] == "nested" for row in failed
        )


@pytest.mark.parametrize("denied_name", ["catalog.json", "segment"])
def test_unreadable_journal_access_stop_hides_unverified_entries_until_repair(
    env, text_source, monkeypatch, denied_name
):
    """Not run on 1 November 2026. An unreadable journal must not resurrect a denial."""
    import errno
    from uuid import uuid4 as new_id

    from mnemion.connectors import source_files
    from mnemion.connectors.config import ConnectorConfig
    from mnemion.journal.format import JournalCatalog, JournalEntry
    from mnemion.service.connector_models import SyncRequestInput

    service, connection, people, config = text_source
    payload = config.model_dump(mode="json")
    payload["provider"]["max_file_bytes"] = 100000
    config = ConnectorConfig.model_validate(payload)
    root = config.provider.path
    (root / "a-kept.md").write_text("Postgres ordinary neighbor", encoding="utf-8")
    (root / "z-later.md").write_text("Postgres later journal file", encoding="utf-8")
    tenant, source_space, writer = new_id(), new_id(), new_id()
    kept = JournalEntry(
        id=new_id(),
        ts="2026-10-01T10:20:30Z",
        tenant_id=tenant,
        space_id=source_space,
        memory_id=new_id(),
        version=1,
        writer=writer,
        subject="Kept",
        text="Postgres journal kept",
    )
    secret = JournalEntry(
        id=new_id(),
        ts="2026-10-01T10:20:30Z",
        tenant_id=tenant,
        space_id=source_space,
        memory_id=new_id(),
        version=1,
        writer=writer,
        subject="Secret",
        text="Postgres journal withdrawn",
    )
    denial = JournalEntry.model_validate(
        {
            **secret.model_dump(),
            "id": str(new_id()),
            "version": 2,
            "action": "forget",
            "text": None,
            "subject": None,
            "metadata": {},
        }
    )
    segment = root / kept.relative_path
    segment.parent.mkdir()
    segment.write_bytes(kept.line() + secret.line() + denial.line())
    catalog = JournalCatalog(tenant_id=tenant, space_id=source_space, records=3)
    (root / "catalog.json").write_bytes(catalog.encoded())
    target = "catalog.json" if denied_name == "catalog.json" else segment.name
    relative = "catalog.json" if denied_name == "catalog.json" else kept.relative_path
    denied = {"on": False}

    def blocked(name):
        if denied["on"] and name == target:
            return PermissionError(errno.EACCES, "PRIVATE_OS_STRING", "hidden")
        return None

    env.identities.grant(
        env.owner,
        env.space,
        people["reader"][0].principal_id,
        GrantInput(role="reader"),
    )
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Postgres native journal neighbor"),
        "field47-journal-neighbor",
    )
    patch_selected_reads(monkeypatch, source_files, blocked)
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
        Client(url, people["reader"][1]) as reader,
    ):
        assert sync(config, client=client)["completed"]
        first = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(first["space_id"])
        journal = _item_for_text(env, people, space, reader, "journal kept")
        later = _item_for_text(env, people, space, reader, "later journal file")
        assert "journal kept" in _texts(reader) and "journal withdrawn" not in _texts(reader)
        status = service.sync_status(env.owner, connection)
        service.request_sync(
            env.owner,
            connection,
            SyncRequestInput(expected_generation=status["requested_generation"]),
        )
        denied["on"] = True
        report = sync(config, client=client)
        assert not report["completed"] and report["removed"] == 0
        scope = report["scopes"][0]
        assert scope["error_code"] == "source_permission_denied"
        assert scope["checkpoint_committed"] is False and scope["incomplete_inventory"]
        assert scope["file_errors"][0]["path"] == relative
        assert scope["file_errors"][0]["error_code"] == "source_permission_denied"
        rendered = json.dumps(report)
        assert "PRIVATE_OS_STRING" not in rendered and "journal withdrawn" not in rendered
        assert service.sync_status(env.owner, connection)["last_successful"] is False
        _refresh_root(service, people, connection, first["external_id"])
        visible = _texts(reader)
        assert "ordinary neighbor" in visible and "native journal neighbor" in visible
        assert "journal kept" not in visible and "journal withdrawn" not in visible
        if denied_name == "catalog.json":
            assert "later journal file" not in visible
            assert _connector_items(env, people, space)[later["memory_id"]]["withheld_at"]
        else:
            assert "later journal file" in visible
        assert _connector_items(env, people, space)[journal["memory_id"]]["withheld_at"]
        assert (
            service.scopes(people["capture"][0], connection)["items"][0]["completed_at"]
            == (first["completed_at"])
        )
        denied["on"] = False
        repaired = sync(config, client=client)
        assert repaired["completed"] and repaired["removed"] == 0
        restored = _texts(reader)
        assert "journal kept" in restored and "journal withdrawn" not in restored
        assert "later journal file" in restored and "ordinary neighbor" in restored
        healed = _connector_items(env, people, space)
        assert healed[journal["memory_id"]]["withheld_at"] is None
        assert healed[journal["memory_id"]]["origin_revision"] == journal["origin_revision"]
        with env.db.transaction(people["capture"][0]) as conn:
            failed = conn.execute(
                """SELECT result->'file_errors' AS errors FROM mnemion.connector_runs
                   WHERE space_id=%s AND state='completed'
                     AND result->>'incomplete_inventory'='true'""",
                (space,),
            ).fetchall()
        assert failed and failed[0]["errors"][0]["path"] == relative


def test_directory_abort_does_not_suspend_another_runners_lease(env, text_source, monkeypatch):
    """Not run on 1 November 2026. A competing lease is not an inventory abort."""
    import errno
    import os
    from pathlib import Path

    from mnemion.connectors import providers
    from service_tests.test_connectors import begin

    service, connection, people, config = text_source
    root = config.provider.path
    (root / "a-kept.md").write_text("Postgres kept during busy lease", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / "old.md").write_text("Postgres busy directory", encoding="utf-8")
    real_scandir = providers.os.scandir
    deny = {"on": False}

    def scandir(path):
        if deny["on"] and Path(path).name == "nested":
            raise PermissionError(errno.EACCES, "PRIVATE_OS_STRING", os.fspath(path))
        return real_scandir(path)

    monkeypatch.setattr(providers.os, "scandir", scandir)
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
    ):
        assert sync(config, client=client)["completed"]
        # Armed only after the first inventory. A busy scope must not record
        # this failure or suspend the other run.
        deny["on"] = True
        first = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(first["space_id"])
        running = begin(service, people["capture"][0], space)
        busy = sync(config, client=client)
        assert not busy["completed"]
        assert busy["scopes"][0]["error_code"] == "connector_busy"
        assert not busy["scopes"][0].get("access_suspended")
        assert "file_errors" not in busy["scopes"][0]
        with env.db.transaction(people["capture"][0]) as conn:
            state = conn.execute(
                "SELECT state FROM mnemion.connector_runs WHERE id=%s", (running,)
            ).fetchone()
            assert state["state"] == "running"
            scope_row = conn.execute(
                "SELECT suspended_at FROM mnemion.connector_scopes WHERE space_id=%s",
                (space,),
            ).fetchone()
            assert scope_row["suspended_at"] is None
        held = _connector_items(env, people, space)
        assert all(row["withheld_at"] is None for row in held.values())
        assert all(row["state"] != "deleted" for row in held.values())
        inventory = service.scopes(people["capture"][0], connection)["items"][0]["inventory"]
        assert not inventory.get("file_errors")
        assert inventory.get("incomplete_inventory") is False


def test_access_stop_keeps_a_slot_after_fifty_content_skips(env, text_source, monkeypatch):
    """Fifty readable skips must not push the directory abort out of the receipt."""
    import errno
    import os
    from pathlib import Path

    from mnemion.connectors import providers
    from mnemion.service.connector_models import SyncRequestInput

    service, connection, people, config = text_source
    root = config.provider.path
    (root / "a-kept.md").write_text("Postgres kept before bounded abort", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / "old.md").write_text("Postgres indexed before bounded abort", encoding="utf-8")
    env.identities.grant(
        env.owner,
        env.space,
        people["reader"][0].principal_id,
        GrantInput(role="reader"),
    )
    deny = {"on": False}
    real_scandir = providers.os.scandir

    def scandir(path):
        if deny["on"] and Path(path).name == "nested":
            raise PermissionError(errno.EACCES, "PRIVATE_OS_STRING", os.fspath(path))
        return real_scandir(path)

    monkeypatch.setattr(providers.os, "scandir", scandir)
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
        Client(url, people["reader"][1]) as reader,
    ):
        assert sync(config, client=client)["completed"]
        first = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(first["space_id"])
        old = _item_for_text(env, people, space, reader, "indexed before bounded abort")
        kept = _item_for_text(env, people, space, reader, "kept before bounded abort")
        for number in range(50):
            (root / f"bad-{number:02}.md").write_bytes(b"\xff")
        status = service.sync_status(env.owner, connection)
        service.request_sync(
            env.owner,
            connection,
            SyncRequestInput(expected_generation=status["requested_generation"]),
        )
        deny["on"] = True
        report = sync(config, client=client)
        assert not report["completed"] and report["removed"] == 0
        scope = report["scopes"][0]
        assert scope["error_code"] == "source_permission_denied"
        assert scope["incomplete_inventory"] and scope["checkpoint_committed"] is False
        assert scope["skipped_documents"] == 51
        assert len(scope["file_errors"]) == 50
        assert {
            "path": "nested",
            "error_code": "source_permission_denied",
            "path_sha256": hashlib.sha256(b"nested").hexdigest(),
        } in scope["file_errors"]
        assert service.sync_status(env.owner, connection)["pending"]
        current = service.scopes(people["capture"][0], connection)["items"][0]
        assert current["completed_at"] == first["completed_at"]
        assert current["checkpoint"] == first["checkpoint"]
        held = _connector_items(env, people, space)
        assert held[old["memory_id"]]["withheld_at"] is not None
        assert held[kept["memory_id"]]["withheld_at"] is None
        assert all(row["state"] != "deleted" for row in held.values())
        _refresh_root(service, people, connection, first["external_id"])
        visible = _texts(reader)
        assert "kept before bounded abort" in visible
        assert "indexed before bounded abort" not in visible
        durable = service.scopes(people["capture"][0], connection)["items"][0]
        assert durable["completed_at"] == first["completed_at"]
        assert len(durable["inventory"]["file_errors"]) == 50
        assert any(
            error["error_code"] == "source_permission_denied" and error.get("path") == "nested"
            for error in durable["inventory"]["file_errors"]
        )
        deny["on"] = False
        for path in root.glob("bad-*.md"):
            path.unlink()
        repaired = sync(config, client=client)
        assert repaired["completed"] and repaired["removed"] == 0 and repaired["changed"] == 0
        restored = _connector_items(env, people, space)
        assert restored[old["memory_id"]]["withheld_at"] is None
        assert restored[old["memory_id"]]["origin_revision"] == old["origin_revision"]
        assert restored[kept["memory_id"]]["origin_revision"] == kept["origin_revision"]
        assert "indexed before bounded abort" in _texts(reader)
        assert not service.sync_status(env.owner, connection)["pending"]


def test_finished_abort_does_not_suspend_a_later_owned_run(env, text_source, monkeypatch):
    """Replay A's stored receipt before any access refresh or B. Later replay, transport, and a busy rejection must leave B active."""
    import errno
    import os
    from pathlib import Path

    from mnemion.connectors import providers
    from mnemion.service.connector_models import FinishInput
    from service_tests.test_connectors import begin

    service, connection, people, config = text_source
    root = config.provider.path
    (root / "a-kept.md").write_text("Postgres kept during later run", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / "old.md").write_text("Postgres hidden during later run", encoding="utf-8")
    deny = {"on": False}
    real_scandir = providers.os.scandir

    def scandir(path):
        if deny["on"] and Path(path).name == "nested":
            raise PermissionError(errno.EACCES, "PRIVATE_OS_STRING", os.fspath(path))
        return real_scandir(path)

    monkeypatch.setattr(providers.os, "scandir", scandir)
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
    ):
        assert sync(config, client=client)["completed"]
        first = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(first["space_id"])
        operator = people["capture"][0]
        stale = begin(service, operator, space)
        with env.db.transaction(operator) as conn:
            conn.execute(
                "UPDATE mnemion.connector_runs SET lease_until=now()-interval '1 second' WHERE id=%s",
                (stale,),
            )
        with pytest.raises(ServiceError) as expired:
            service.finish(
                operator,
                space,
                stale,
                FinishInput(
                    skipped_documents=1,
                    file_errors=[{"error_code": "source_permission_denied"}],
                ),
            )
        assert expired.value.code == "run_inactive"
        with env.db.transaction(operator) as conn:
            expired_row = conn.execute(
                "SELECT state, result FROM mnemion.connector_runs WHERE id=%s", (stale,)
            ).fetchone()
            scope_row = conn.execute(
                "SELECT suspended_at FROM mnemion.connector_scopes WHERE space_id=%s",
                (space,),
            ).fetchone()
        assert expired_row["state"] == "running" and expired_row["result"] is None
        assert scope_row["suspended_at"] is None
        original = client.request
        captured = {}
        armed = {"on": False}

        def effects(run_id):
            with env.db.transaction(operator) as conn:
                run = conn.execute(
                    """SELECT state, result, finished_at, lease_until
                       FROM mnemion.connector_runs WHERE id=%s""",
                    (run_id,),
                ).fetchone()
                scope_row = conn.execute(
                    """SELECT suspended_at, suspension_reason, access_valid_until,
                              checkpoint, completed_at
                       FROM mnemion.connector_scopes WHERE space_id=%s""",
                    (space,),
                ).fetchone()
                audits = conn.execute(
                    """SELECT action, count(*) AS n FROM mnemion.audit_events
                       WHERE space_id=%s
                         AND action IN ('connector.access_suspended','connector.synced')
                       GROUP BY action ORDER BY action""",
                    (space,),
                ).fetchall()
                runs = conn.execute(
                    "SELECT count(*) AS n FROM mnemion.connector_runs WHERE space_id=%s",
                    (space,),
                ).fetchone()
            return {
                "run": (run["state"], run["result"], run["finished_at"], run["lease_until"]),
                "suspended_at": scope_row["suspended_at"],
                "suspension_reason": scope_row["suspension_reason"],
                "access_valid_until": scope_row["access_valid_until"],
                "checkpoint": scope_row["checkpoint"],
                "completed_at": scope_row["completed_at"],
                "audits": tuple((row["action"], row["n"]) for row in audits),
                "runs": runs["n"],
                "items": {
                    key: (
                        row["withheld_at"],
                        row["state"],
                        row["validated_run"],
                        row["origin_revision"],
                    )
                    for key, row in _connector_items(env, people, space).items()
                },
            }

        def inject(method, path, **kwargs):
            result = original(method, path, **kwargs)
            if armed["on"] and method == "POST" and str(path).endswith("/finish") and not captured:
                captured["path"] = path
                captured["body"] = kwargs.get("body")
                captured["result"] = result
                finished = UUID(result["run_id"])
                captured["before"] = effects(finished)
                captured["immediate"] = original(
                    "POST",
                    path,
                    body=kwargs.get("body"),
                    key=kwargs.get("key"),
                )
                captured["after"] = effects(finished)
                _refresh_root(service, people, connection, first["external_id"])
                captured["run"] = begin(service, operator, space)
            return result

        client.request = inject
        deny["on"] = True
        armed["on"] = True
        report = sync(config, client=client)
        stored = captured["before"]["run"][1]
        assert captured["immediate"] == captured["result"]
        assert captured["immediate"]["run_id"] == stored["run_id"]
        assert captured["immediate"]["access_suspended"] is True
        assert stored["access_suspended"] is True
        assert captured["before"]["suspended_at"] is not None
        assert captured["after"] == captured["before"]
        assert captured["run"] != UUID(report["scopes"][0]["run_id"])
        scope = report["scopes"][0]
        assert scope["error_code"] == "source_permission_denied" and scope["access_suspended"]
        assert scope["file_errors"][0]["path"] == "nested"

        def active(run_id):
            with env.db.transaction(operator) as conn:
                run = conn.execute(
                    "SELECT state, lease_until>now() AS lease_current FROM mnemion.connector_runs WHERE id=%s",
                    (run_id,),
                ).fetchone()
                scope_row = conn.execute(
                    "SELECT suspended_at FROM mnemion.connector_scopes WHERE space_id=%s",
                    (space,),
                ).fetchone()
            return run, scope_row

        run, scope_row = active(captured["run"])
        assert run["state"] == "running" and run["lease_current"]
        assert scope_row["suspended_at"] is None
        held = {
            key: (row["withheld_at"], row["state"], row["validated_run"], row["origin_revision"])
            for key, row in _connector_items(env, people, space).items()
        }
        assert any(row[0] is not None for row in held.values())
        replay = original(
            "POST",
            captured["path"],
            body=captured["body"],
            key="replay-owned-abort",
        )
        assert replay["run_id"] == captured["result"]["run_id"]
        assert replay["access_suspended"] is True
        run, scope_row = active(captured["run"])
        assert run["state"] == "running" and run["lease_current"]
        assert scope_row["suspended_at"] is None
        again = {
            key: (row["withheld_at"], row["state"], row["validated_run"], row["origin_revision"])
            for key, row in _connector_items(env, people, space).items()
        }
        assert again == held

        def transport(method, path, **kwargs):
            if method == "POST" and str(path).endswith("/runs"):
                raise httpx.ConnectError("synthetic transport")
            return original(method, path, **kwargs)

        client.request = transport
        failed = sync(config, client=client)
        assert not failed["completed"]
        assert failed["scopes"][0]["error_code"] == "source_read_failed"
        assert "file_errors" not in failed["scopes"][0]
        assert not failed["scopes"][0].get("access_suspended")
        run, scope_row = active(captured["run"])
        assert run["state"] == "running" and run["lease_current"]
        assert scope_row["suspended_at"] is None
        latest = service.scopes(operator, connection)["items"][0]["inventory"]
        assert latest["file_errors"][0]["path"] == "nested"
        after_transport = {
            key: (row["withheld_at"], row["state"], row["validated_run"], row["origin_revision"])
            for key, row in _connector_items(env, people, space).items()
        }
        assert after_transport == held
        client.request = original
        rejected = sync(config, client=client)
        assert not rejected["completed"]
        assert rejected["scopes"][0]["error_code"] == "connector_busy"
        assert "file_errors" not in rejected["scopes"][0]
        assert not rejected["scopes"][0].get("access_suspended")
        run, scope_row = active(captured["run"])
        assert run["state"] == "running" and run["lease_current"]
        assert scope_row["suspended_at"] is None
        after_service = {
            key: (row["withheld_at"], row["state"], row["validated_run"], row["origin_revision"])
            for key, row in _connector_items(env, people, space).items()
        }
        assert after_service == held
        assert (
            service.scopes(operator, connection)["items"][0]["inventory"]["file_errors"][0]["path"]
            == "nested"
        )


def test_unencodable_directory_name_keeps_a_category_only_hold(env, text_source, monkeypatch):
    """A surrogate directory name is withheld without a path or OS message."""
    import errno
    import os
    from pathlib import Path

    from mnemion.connectors import providers
    from mnemion.connectors.source_files import relative_evidence

    service, connection, people, config = text_source
    root = config.provider.path
    (root / "old.md").write_text("Postgres surrogate unread", encoding="utf-8")
    env.identities.grant(
        env.owner,
        env.space,
        people["reader"][0].principal_id,
        GrantInput(role="reader"),
    )
    safe = relative_evidence("nested/ok.md")
    assert safe == {
        "path": "nested/ok.md",
        "path_sha256": hashlib.sha256(b"nested/ok.md").hexdigest(),
    }
    assert relative_evidence("bad-\udcff") == {}
    real_walk = providers.os.walk
    armed = {"on": False}

    def walk(top, onerror=None, followlinks=False):
        if not armed["on"]:
            yield from real_walk(top, onerror=onerror, followlinks=followlinks)
            return
        if onerror is not None:
            onerror(
                PermissionError(
                    errno.EACCES,
                    "PRIVATE_OS_STRING",
                    os.fspath(Path(top) / "bad-\udcff"),
                )
            )
        return
        yield

    monkeypatch.setattr(providers.os, "walk", walk)
    with (
        serve(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, people["capture"][1]) as client,
        Client(url, people["reader"][1]) as reader,
    ):
        assert sync(config, client=client)["completed"]
        first = service.scopes(people["capture"][0], connection)["items"][0]
        space = UUID(first["space_id"])
        old = _item_for_text(env, people, space, reader, "surrogate unread")
        armed["on"] = True
        report = sync(config, client=client)
        assert not report["completed"] and report["removed"] == 0
        scope = report["scopes"][0]
        assert scope["error_code"] == "source_permission_denied"
        assert scope["access_suspended"] and scope["checkpoint_committed"] is False
        assert len(scope["file_errors"]) == 1
        diagnostic = scope["file_errors"][0]
        assert diagnostic["error_code"] == "source_permission_denied"
        assert diagnostic.get("path") is None
        assert diagnostic.get("path_sha256") is None
        rendered = json.dumps(report)
        assert "PRIVATE_OS_STRING" not in rendered and "\\udcff" not in rendered
        assert str(root) not in rendered
        _refresh_root(service, people, connection, first["external_id"])
        assert "surrogate unread" not in _texts(reader)
        assert _connector_items(env, people, space)[old["memory_id"]]["withheld_at"] is not None
        durable = service.scopes(people["capture"][0], connection)["items"][0]
        assert durable["completed_at"] == first["completed_at"]
        assert durable["inventory"]["file_errors"] == [{"error_code": "source_permission_denied"}]
