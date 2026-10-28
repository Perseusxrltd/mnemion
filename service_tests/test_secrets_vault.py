"""Real database tests for secret access, ciphertext integrity and recovery."""

from concurrent.futures import ThreadPoolExecutor
import json
import time
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from mnemion.service import recovery
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.db import Database
from mnemion.service.models import KeyInput, PrincipalInput
from mnemion.service.vault import VaultService
from mnemion.service.vault_crypto import VaultSettings, new_vault_key
from mnemion.service.vault_models import (
    VaultAuditorChange,
    VaultDelete,
    VaultExport,
    VaultGrant,
    VaultImport,
    VaultPut,
)
from service_tests.test_administration_continuity import authorization
from service_tests.test_mcp_compatibility import call, request
from service_tests.test_recovery import destination as destination

VALUE = "synthetic-vault-only-credential-never-searchable"


@pytest.fixture
def vault(env):
    return VaultService(env.db, VaultSettings(key=new_vault_key(), enabled=True))


def create(vault, owner, *, name="Fixture credential", value=VALUE):
    entry = uuid4()
    return vault.put(owner, entry, VaultPut(expected_version=0, name=name, value=value))


def member(env, *, administrator=False, kind="application"):
    principal = env.identities.create_principal(
        env.owner, PrincipalInput(name="Fixture member", kind=kind, administrator=administrator)
    )
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="Fixture key"))
    return env.db.authenticate(key["api_key"]), key["api_key"]


def allow(vault, owner, entry, identity, *, read=False, write=False, remove=False):
    grants = vault.grants(owner, UUID(entry["id"]))
    return vault.grant(
        owner,
        UUID(entry["id"]),
        VaultGrant(
            expected_access_version=grants["access_version"],
            subject_kind="key",
            subject_id=identity.key_id,
            read=read,
            write=write,
            remove=remove,
        ),
    )


def test_values_are_encrypted_and_absent_from_memory_search_context_exports_and_logs(env, vault):
    entry = create(vault, env.owner)
    assert VALUE not in json.dumps(entry)
    assert VALUE not in json.dumps(vault.list(env.owner))
    assert vault.get(env.owner, UUID(entry["id"]))["value"] == VALUE
    with psycopg.connect(env.admin_dsn) as conn:
        record = conn.execute(
            "SELECT nonce,ciphertext FROM mnemion.vault_entries WHERE id=%s", (entry["id"],)
        ).fetchone()
        assert len(record[0]) == 12 and VALUE.encode() not in bytes(record[1])
        for table in (
            "memories",
            "memory_revisions",
            "sources",
            "source_revisions",
            "jobs",
            "embeddings",
            "core_blocks",
        ):
            assert (
                conn.execute(
                    f"SELECT count(*) FROM mnemion.{table} WHERE tenant_id=%s",
                    (env.owner.tenant_id,),
                ).fetchone()[0]
                == 0
            )
    app = create_app(
        env.db, env.embedder, vault_settings=vault.settings, mcp_enabled=False, studio_enabled=False
    )
    with TestClient(app) as api:
        headers = authorization(env.token)
        found = api.post(
            "/v1/recall",
            headers=headers,
            json={"query": VALUE, "all_accessible": True, "mode": "lexical"},
        )
        assert found.status_code == 200 and not found.json()["hits"]
        context = api.post(
            "/v1/context",
            headers=headers,
            json={"query": VALUE, "all_accessible": True, "mode": "lexical"},
        )
        assert context.status_code == 200 and VALUE not in context.text
        exported = api.post("/v1/exports", headers=headers, json={"all_accessible": True})
        assert exported.status_code == 200 and VALUE.encode() not in exported.content
        revealed = api.get(f"/v1/vault/entries/{entry['id']}", headers=headers)
        assert revealed.status_code == 200 and revealed.headers["cache-control"] == "no-store"
    audit = vault.audit_events(env.owner)
    assert VALUE not in json.dumps(audit) and "Fixture credential" not in json.dumps(audit)
    assert any(
        row["action"] == "get"
        and row["entry_id"] == entry["id"]
        and row["key_id"] == str(env.owner.key_id)
        for row in audit["items"]
    )


def test_key_grants_distinguish_list_read_and_write_and_do_not_follow_other_keys(env, vault):
    entry = create(vault, env.owner)
    writer, _ = member(env)
    second = env.identities.create_key(env.owner, writer.principal_id, KeyInput(name="Not granted"))
    second_identity = env.db.authenticate(second["api_key"])
    assert vault.list(writer)["items"] == []
    allow(vault, env.owner, entry, writer)
    assert len(vault.list(writer)["items"]) == 1
    with pytest.raises(ServiceError) as denied:
        vault.get(writer, UUID(entry["id"]))
    assert denied.value.status == 403
    allow(vault, env.owner, entry, writer, write=True)
    written = vault.put(
        writer,
        UUID(entry["id"]),
        VaultPut(expected_version=1, name=entry["name"], value="replacement-fixture"),
    )
    assert written["version"] == 2 and not written["permissions"]["read"]
    assert vault.list(second_identity)["items"] == []
    with pytest.raises(ServiceError):
        vault.get(writer, UUID(entry["id"]))
    allow(vault, env.owner, entry, writer, read=True)
    assert vault.get(writer, UUID(entry["id"]))["value"] == "replacement-fixture"
    with pytest.raises(ServiceError) as denied:
        vault.put(
            writer,
            UUID(entry["id"]),
            VaultPut(expected_version=2, name=entry["name"], value="not-authorized"),
        )
    assert denied.value.status == 403
    allow(vault, env.owner, entry, writer, remove=True)
    assert vault.list(writer)["items"] == []
    assert any(
        row["outcome"] == "denied" and row["key_id"] == str(writer.key_id)
        for row in vault.audit_events(env.owner)["items"]
    )


def test_administrator_does_not_implicitly_read_a_value(env, vault):
    entry = create(vault, env.owner)
    admin, _ = member(env, administrator=True, kind="human")
    assert len(vault.list(admin)["items"]) == 1
    with pytest.raises(ServiceError) as denied:
        vault.get(admin, UUID(entry["id"]))
    assert denied.value.status == 403
    allow(vault, admin, entry, admin, read=True)
    assert vault.get(admin, UUID(entry["id"]))["value"] == VALUE


def test_person_grant_follows_signed_in_devices_but_not_personal_api_keys(env, vault):
    from service_tests.test_individual_sign_in import enroll, sign_in

    service = enroll(env)
    first = env.db.authenticate(sign_in(env, service)["access_token"])
    second = env.db.authenticate(sign_in(env, service)["access_token"])
    entry = create(vault, first)
    assert vault.get(second, UUID(entry["id"]))["value"] == VALUE
    with pytest.raises(ServiceError) as denied:
        vault.get(env.owner, UUID(entry["id"]))
    assert denied.value.status == 403
    assert vault.grants(first, UUID(entry["id"]))["items"][0]["subject_kind"] == "person"
    service.revoke(first, second.session_id)
    with pytest.raises(ServiceError) as denied:
        vault.get(second, UUID(entry["id"]))
    assert denied.value.status == 401


def test_other_tenant_and_indexing_worker_cannot_access_vault(env, vault):
    entry = create(vault, env.owner)
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Other",
        administrator_name="Other owner",
        generation=env.embedder.generation,
    )
    identity = env.db.authenticate(other["api_key"])
    assert vault.list(identity)["items"] == []
    for action in (
        lambda: vault.get(identity, UUID(entry["id"])),
        lambda: vault.delete(identity, UUID(entry["id"]), VaultDelete(expected_version=1)),
    ):
        with pytest.raises(ServiceError) as denied:
            action()
        assert denied.value.status == 404
    with pytest.raises(ServiceError) as denied:
        allow(vault, env.owner, entry, identity, read=True)
    assert denied.value.code == "vault_grant_subject"
    with env.db.transaction(identity) as conn:
        vault._scope(conn, identity)
        assert conn.execute("SELECT * FROM mnemion.vault_entries").fetchall() == []
    for table in ("vault_entries", "vault_grants", "vault_denials", "vault_audit_events"):
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            env.worker_db.worker_transaction(env.owner.tenant_id) as conn,
        ):
            conn.execute(f"SELECT * FROM mnemion.{table}")


@pytest.mark.parametrize(
    "mutation", ["ciphertext", "nonce", "name", "version", "tenant_id", "id", "key_id"]
)
def test_authenticated_envelope_rejects_substitution(env, vault, mutation):
    entry = create(vault, env.owner)
    with env.db.transaction(env.owner) as conn:
        row = conn.execute(
            "SELECT * FROM mnemion.vault_entries WHERE id=%s", (entry["id"],)
        ).fetchone()
    if mutation in {"ciphertext", "nonce"}:
        data = bytearray(row[mutation])
        data[-1] ^= 1
        row[mutation] = bytes(data)
    elif mutation in {"tenant_id", "id"}:
        row[mutation] = uuid4()
    elif mutation == "version":
        row[mutation] += 1
    elif mutation == "key_id":
        row[mutation] = "0" * 32
    else:
        row[mutation] = "Changed label"
    with pytest.raises(ServiceError):
        vault.cipher.decrypt(row)


def test_concurrent_writes_and_acl_changes_refuse_stale_versions(env, vault):
    entry = create(vault, env.owner)

    def replace(value):
        try:
            return vault.put(
                env.owner,
                UUID(entry["id"]),
                VaultPut(expected_version=1, name=entry["name"], value=value),
            )["version"]
        except ServiceError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(replace, ["first-fixture", "second-fixture"])) == [2, 409]
    reader, _ = member(env)
    grant = VaultGrant(
        expected_access_version=1, subject_kind="key", subject_id=reader.key_id, read=True
    )
    vault.grant(env.owner, UUID(entry["id"]), grant)
    with pytest.raises(ServiceError) as stale:
        vault.grant(env.owner, UUID(entry["id"]), grant)
    assert stale.value.code == "vault_access_changed"


def test_revocation_is_rechecked_after_waiting_for_an_administrator(env, vault):
    entry = create(vault, env.owner)
    reader, _ = member(env)
    allow(vault, env.owner, entry, reader, read=True)
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"administrator-access:{env.owner.tenant_id}",),
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(vault.get, reader, UUID(entry["id"]))
            try:
                deadline = time.monotonic() + 5
                while not conn.execute(
                    "SELECT 1 FROM pg_stat_activity WHERE wait_event='advisory' AND pid<>pg_backend_pid() LIMIT 1"
                ).fetchone():
                    if time.monotonic() >= deadline:
                        pytest.fail("The credential read did not reach the revocation lock")
                    time.sleep(0.01)
                conn.execute(
                    "UPDATE mnemion.api_keys SET revoked_at=clock_timestamp() WHERE id=%s",
                    (reader.key_id,),
                )
                conn.commit()
            finally:
                conn.rollback()
            with pytest.raises(ServiceError) as revoked:
                future.result(timeout=10)
            assert revoked.value.status == 401


def test_encrypted_export_restore_uses_new_ids_and_grants_and_is_all_or_nothing(env, vault):
    first = create(vault, env.owner)
    second = create(vault, env.owner, name="Second fixture")
    recovery = new_vault_key()
    export = vault.export(
        env.owner, VaultExport(entry_ids=[first["id"], second["id"]], recovery_key=recovery)
    )
    assert VALUE not in json.dumps(export) and first["name"] not in json.dumps(export)
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Restore",
        administrator_name="New owner",
        generation=env.embedder.generation,
    )
    owner = env.db.authenticate(other["api_key"])
    recovered = vault.import_archive(owner, VaultImport(archive=export, recovery_key=recovery))
    assert len(recovered["items"]) == 2 and first["id"] not in {
        item["id"] for item in recovered["items"]
    }
    for item in recovered["items"]:
        assert vault.get(owner, UUID(item["id"]))["value"] == VALUE
        assert {
            grant["subject_id"] for grant in vault.grants(owner, UUID(item["id"]))["items"]
        } == {str(owner.key_id)}
    with pytest.raises(ServiceError) as collision:
        vault.import_archive(owner, VaultImport(archive=export, recovery_key=recovery))
    assert collision.value.code == "vault_name_exists" and len(vault.list(owner)["items"]) == 2
    with pytest.raises(ServiceError) as wrong:
        vault.import_archive(owner, VaultImport(archive=export, recovery_key=new_vault_key()))
    assert wrong.value.code == "vault_archive_invalid"


def test_delete_purges_ciphertext_and_refuses_reuse(env, vault):
    entry = create(vault, env.owner)
    vault.delete(env.owner, UUID(entry["id"]), VaultDelete(expected_version=1))
    assert vault.list(env.owner)["items"] == []
    with psycopg.connect(env.admin_dsn) as conn:
        assert conn.execute(
            "SELECT nonce,ciphertext FROM mnemion.vault_entries WHERE id=%s", (entry["id"],)
        ).fetchone() == (None, None)
        assert (
            conn.execute(
                "SELECT FROM mnemion.vault_denials WHERE entry_id=%s", (entry["id"],)
            ).fetchone()
            is not None
        )
    with pytest.raises(ServiceError) as refused:
        vault.put(
            env.owner,
            UUID(entry["id"]),
            VaultPut(expected_version=0, name=entry["name"], value="cannot-resurrect"),
        )
    assert refused.value.code == "vault_entry_exists"


@pytest.mark.parametrize(
    "settings,code",
    [
        (VaultSettings(), "vault_disabled"),
        (VaultSettings(enabled=True), "vault_key_missing"),
        (VaultSettings(enabled=True, key="invalid-fixture-key"), "vault_key_invalid"),
    ],
)
def test_bad_vault_configuration_keeps_values_closed_and_permitted_metadata_inspectable(
    env, settings, code
):
    with TestClient(
        create_app(
            env.db, env.embedder, vault_settings=settings, mcp_enabled=False, studio_enabled=False
        )
    ) as api:
        headers = authorization(env.token)
        assert api.get("/v1/me", headers=headers).status_code == 200
        status = api.get("/v1/vault/status", headers=headers).json()
        assert not status["available"] and status["error_code"] == code
        assert status["metadata_available"] == settings.enabled
        listing = api.get("/v1/vault/entries", headers=headers)
        assert listing.status_code == (200 if settings.enabled else 503)
        if settings.enabled:
            assert listing.json()["items"] == []
        assert api.get(f"/v1/vault/entries/{uuid4()}", headers=headers).status_code == 503


def test_wrong_host_key_cannot_silently_create_a_second_key_family(env, vault):
    create(vault, env.owner)
    changed = VaultService(env.db, VaultSettings(enabled=True, key=new_vault_key()))
    assert changed.status(env.owner)["error_code"] == "vault_key_unavailable"
    with pytest.raises(ServiceError) as refused:
        create(changed, env.owner, name="Wrong family")
    assert refused.value.code == "vault_key_unavailable"


def test_http_validation_does_not_echo_secrets_and_status_has_no_key(env, vault):
    with TestClient(
        create_app(
            env.db,
            env.embedder,
            vault_settings=vault.settings,
            mcp_enabled=False,
            studio_enabled=False,
        )
    ) as api:
        headers = authorization(env.token)
        assert api.get("/v1/vault/entries").status_code == 401
        rejected = api.put(
            f"/v1/vault/entries/{uuid4()}",
            headers=headers,
            json={"expected_version": -1, "name": "Fixture", "value": VALUE, "unexpected": VALUE},
        )
        assert rejected.status_code == 422 and VALUE not in rejected.text
        assert (
            vault.settings.key.get_secret_value()
            not in api.get("/v1/vault/status", headers=headers).text
        )


def test_recovery_reconciles_later_deletions_and_strips_old_grants(env, vault):
    from mnemion.service.recovery import _ledger
    from mnemion.service.vault_recovery import restore

    entry = create(vault, env.owner)
    with psycopg.connect(env.admin_dsn, row_factory=psycopg.rows.dict_row) as conn:
        old = conn.execute(
            "SELECT * FROM mnemion.vault_entries WHERE id=%s", (entry["id"],)
        ).fetchone()
    vault.delete(env.owner, UUID(entry["id"]), VaultDelete(expected_version=1))
    survivor = create(vault, env.owner, name="Surviving credential")
    with psycopg.connect(env.admin_dsn, row_factory=psycopg.rows.dict_row) as conn:
        ledger = _ledger(conn)
        conn.execute("DELETE FROM mnemion.vault_denials WHERE entry_id=%s", (entry["id"],))
        conn.execute(
            "UPDATE mnemion.vault_entries SET nonce=%s,ciphertext=%s,deleted_at=NULL,version=1 WHERE id=%s",
            (old["nonce"], old["ciphertext"], entry["id"]),
        )
        restore(conn, ledger)
        assert (
            conn.execute(
                "SELECT ciphertext FROM mnemion.vault_entries WHERE id=%s", (entry["id"],)
            ).fetchone()["ciphertext"]
            is None
        )
        assert (
            conn.execute(
                "SELECT count(*) AS count FROM mnemion.vault_grants WHERE entry_id=%s",
                (survivor["id"],),
            ).fetchone()["count"]
            == 0
        )
    with pytest.raises(ServiceError):
        vault.get(env.owner, UUID(survivor["id"]))


@pytest.mark.parametrize("profile", ["full", "compact"])
def test_mcp_opt_in_uses_current_grants_and_keeps_values_out_of_listing(
    env, vault, monkeypatch, profile
):
    monkeypatch.setenv("MNEMION_MCP_TOOL_PROFILE", profile)
    settings = vault.settings.model_copy(update={"mcp_enabled": True})
    reader, token = member(env)
    entry_id = str(uuid4())
    with TestClient(
        create_app(env.db, env.embedder, vault_settings=settings, studio_enabled=False),
        base_url="http://127.0.0.1",
    ) as api:
        listing = request(api, env.token, "tools/list").json()["result"]
        assert {"vault_list", "vault_get", "vault_put"} <= {
            tool["name"] for tool in listing["tools"]
        }
        saved = call(
            api,
            env.token,
            "vault_put",
            {"entry_id": entry_id, "name": "MCP fixture", "value": VALUE, "expected_version": 0},
        )
        assert not saved["isError"] and VALUE not in json.dumps(saved)
        invalid = call(
            api,
            env.token,
            "vault_put",
            {"entry_id": entry_id, "name": "MCP fixture", "value": VALUE, "expected_version": -1},
        )
        assert invalid["isError"] and VALUE not in json.dumps(invalid)
        private = call(
            api,
            env.token,
            "mnemion",
            {
                "action": "read",
                "operation": "vault.get",
                "request": {"parameters": {"entry_id": entry_id}},
            },
        )
        assert (
            private["isError"] and private["structuredContent"]["code"] == "private_file_required"
        )
        assert call(api, token, "vault_get", {"entry_id": entry_id})["isError"]
        assert not call(api, token, "vault_list")["structuredContent"]["items"]
        allow(vault, env.owner, {"id": entry_id}, reader, read=True)
        assert VALUE not in json.dumps(call(api, token, "vault_list"))
        assert (
            call(api, token, "vault_get", {"entry_id": entry_id})["structuredContent"]["value"]
            == VALUE
        )
        denied = call(
            api,
            token,
            "vault_put",
            {
                "entry_id": entry_id,
                "name": "MCP fixture",
                "value": "ungranted-change",
                "expected_version": 1,
            },
        )
        assert denied["isError"]
        allow(vault, env.owner, {"id": entry_id}, reader, remove=True)
        assert call(api, token, "vault_get", {"entry_id": entry_id})["isError"]


def test_mcp_disabled_cannot_be_bypassed_through_the_generic_operations(env, vault, monkeypatch):
    monkeypatch.setenv("MNEMION_MCP_TOOL_PROFILE", "compact")
    with TestClient(
        create_app(env.db, env.embedder, vault_settings=vault.settings, studio_enabled=False),
        base_url="http://127.0.0.1",
    ) as api:
        listing = request(api, env.token, "tools/list").json()["result"]
        assert not any(tool["name"].startswith("vault_") for tool in listing["tools"])
        for operation in ("vault.status", "vault.list", "vault.get"):
            result = call(api, env.token, "mnemion", {"action": "read", "operation": operation})
            assert result["isError"] and result["structuredContent"]["code"] == "vault_mcp_disabled"
        assert api.get("/v1/vault/status", headers=authorization(env.token)).json()["available"]


def test_actual_backup_restore_requires_separate_key_and_fresh_grants(
    env, vault, postgres, pg_bin, tmp_path, destination
):
    survivor = create(vault, env.owner)
    doomed = create(vault, env.owner, name="Discarded after snapshot")
    auditor, _ = member(env)
    vault.auditor(env.owner, auditor.key_id, VaultAuditorChange(expected_version=0, enabled=True))
    archive, ledger, credentials = (
        tmp_path / name for name in ("vault.mnemion", "ledger.json", "owner.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    assert VALUE.encode() not in archive.read_bytes()
    assert vault.settings.key.get_secret_value().encode() not in archive.read_bytes()
    vault.delete(env.owner, UUID(doomed["id"]), VaultDelete(expected_version=1))
    recovery.export_ledger(env.admin_dsn, ledger)
    recovery.restore_backup(
        env.admin_dsn,
        archive,
        database_name=destination,
        deletion_ledger=ledger,
        credentials_output=credentials,
        pg_bin=pg_bin,
    )
    db = Database(make_conninfo(postgres[1], dbname=destination))
    db.open()
    try:
        owner = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        identity = db.authenticate(owner["api_key"])
        with pytest.raises(ServiceError):
            db.authenticate(env.token)
        unavailable = VaultService(db, VaultSettings(enabled=True))
        assert not unavailable.status(identity)["available"]
        restored = VaultService(db, vault.settings)
        assert restored.status(identity)["available"]
        with pytest.raises(ServiceError) as denied:
            restored.get(identity, UUID(survivor["id"]))
        assert denied.value.status == 403
        assert restored.grants(identity, UUID(survivor["id"]))["items"] == []
        historical = restored.auditors(identity)["items"]
        assert len(historical) == 1 and not historical[0]["enabled"] and not historical[0]["active"]
        assert historical[0]["key_id"] == str(auditor.key_id) and historical[0]["version"] == 2
        allow(restored, identity, survivor, identity, read=True)
        assert restored.get(identity, UUID(survivor["id"]))["value"] == VALUE
        with pytest.raises(ServiceError) as deleted:
            restored.get(identity, UUID(doomed["id"]))
        assert deleted.value.status == 404
    finally:
        db.close()


def test_private_cli_handles_full_values_and_exports_without_transcript_or_format_leaks(
    env, vault, tmp_path, monkeypatch, capsys
):
    from mnemion import control_cli
    from mnemion.local_state import private_output
    from service_tests.test_clients import running

    large = "synthetic-private-large-value-" + "\0" * 65000
    entry_id = uuid4()
    export_key = new_vault_key()

    def command(name, document, *, private=True):
        request_file, result_file = tmp_path / f"{uuid4()}.json", tmp_path / f"{uuid4()}.json"
        with private_output(request_file) as stream:
            stream.write(json.dumps(document).encode())
        arguments = ["call", name, "--input", str(request_file)]
        if private:
            arguments += ["--result-file", str(result_file)]
        result = control_cli.main(arguments)
        output = capsys.readouterr().out
        assert "synthetic-private-large-value-" not in output and export_key not in output
        if private:
            assert result == 0, output
            return json.loads(result_file.read_text())
        assert result == 1 and not result_file.exists()

    with running(
        create_app(
            env.db,
            env.embedder,
            vault_settings=vault.settings,
            studio_enabled=False,
            mcp_enabled=False,
        )
    ) as url:
        monkeypatch.setenv("MNEMION_API_URL", url)
        monkeypatch.setenv("MNEMION_API_KEY", env.token)
        document = {
            "parameters": {"entry_id": str(entry_id)},
            "body": {"expected_version": 0, "name": "Large private value", "value": large},
        }
        command("vault.put", document, private=False)
        created = command("vault.put", document)
        assert created["version"] == 1
        read = command("vault.get", {"parameters": {"entry_id": str(entry_id)}})
        assert read["value"] == large
        additional = [
            create(vault, env.owner, name=f"Portable export item {index}", value="x" * 50000)
            for index in range(4)
        ]
        entries = [str(entry_id), *(entry["id"] for entry in additional)]
        envelope = command(
            "vault.export", {"body": {"entry_ids": entries, "recovery_key": export_key}}
        )
        assert len(json.dumps(envelope)) > 262144 and "api_url" not in envelope
        assert "synthetic-private-large-value-" not in json.dumps(envelope)
        for entry in entries:
            vault.delete(env.owner, UUID(entry), VaultDelete(expected_version=1))
        imported = command(
            "vault.import", {"body": {"archive": envelope, "recovery_key": export_key}}
        )
        assert len(imported["items"]) == 5
        assert not set(entries) & {entry["id"] for entry in imported["items"]}
        recovered = next(
            entry for entry in imported["items"] if entry["name"] == "Large private value"
        )
        assert vault.get(env.owner, UUID(recovered["id"]))["value"] == large
