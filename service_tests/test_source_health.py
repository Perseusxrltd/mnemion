"""A corrupt text file cannot stop unrelated updates or authorize deletions."""

import hashlib
import json
import subprocess
from uuid import UUID

import httpx
import pytest

from mnemion.connectors.config import ConnectorConfig
from mnemion.connectors.runner import sync
from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service.connector_models import BindingInput, ConnectorInput
from mnemion.service.connectors import ConnectorService
from mnemion.service.errors import ServiceError
from mnemion.service.models import GrantInput, KeyInput, PrincipalInput
from service_tests.test_clients import running as serve


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
