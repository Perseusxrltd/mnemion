"""Independent KDBX fixtures and real vault permissions/transactions, all synthetic."""

import base64
import builtins
import hashlib
import json
from pathlib import Path
import struct
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg.rows import dict_row
import pytest

from mnemion import agent_control, control_cli
from mnemion.local_state import private_output
from mnemion.sdk import Client
from mnemion.service import keepass_codec as codec, keepass_vault
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.keepass_models import (
    KeepassExportInput,
    KeepassImportInput,
    KeepassPreviewInput,
)
from mnemion.service.vault_crypto import VaultCipher, new_vault_key
from mnemion.service.vault_models import VaultDelete, VaultExport, VaultImport, VaultPut
from service_tests.test_administration_continuity import authorization
from service_tests.test_clients import running
from service_tests.test_secrets_vault import allow, create, member, vault as vault

FIXTURES = Path(__file__).parent / "fixtures/keepass"
MANIFEST = json.loads((FIXTURES / "expected.json").read_text())
EXPORT_PASSWORD = "Only-synthetic-export-fixture-47!"


def fixture(name="argon2d-aes.kdbx"):
    expected = MANIFEST["fixtures"][name]
    data = (FIXTURES / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected["sha256"]
    return (
        data,
        expected["password"],
        ((FIXTURES / expected["key_file"]).read_bytes() if expected["key_file"] else None),
        expected,
    )


def source(**changes):
    data, password, key_file, _ = fixture()
    return KeepassPreviewInput(
        **{
            "file": base64.b64encode(data).decode(),
            "password": password,
            "key_file": base64.b64encode(key_file).decode() if key_file else None,
            **changes,
        }
    )


def approve(vault, owner, command=None):
    command = command or source()
    preview = keepass_vault.preview(vault, owner, command)
    approved = KeepassImportInput(
        **command.model_dump(), expected_plan=preview["plan"], import_current_values=True
    )
    return keepass_vault.import_file(vault, owner, approved), approved


def export(vault, owner, items):
    result = keepass_vault.export_file(
        vault,
        owner,
        KeepassExportInput(entry_ids=[item["id"] for item in items], password=EXPORT_PASSWORD),
    )
    data = base64.b64decode(result["file"], validate=True)
    assert hashlib.sha256(data).hexdigest() == result["sha256"]
    return codec.load(data, EXPORT_PASSWORD)


def fields(entries):
    return {
        (entry["id"], field["kind"], field["name"]): field["value"]
        for entry in entries
        for field in entry["fields"]
    }


@pytest.mark.parametrize("name", list(MANIFEST["fixtures"]))
def test_independent_kdbx_algorithms_protected_history_and_current_fields(name):
    data, password, key_file, expected = fixture(name)
    decoded = codec.load(data, password, key_file)
    assert fields(decoded["entries"]) == fields(expected["entries"])
    assert [e["groups"] for e in decoded["entries"]] == [e["groups"] for e in expected["entries"]]
    assert decoded["omitted"] == expected["omitted"]


@pytest.mark.parametrize("name", ["key-v1.key", "key-v2.key", "key-raw.key", "key-hex.key"])
def test_standard_key_file_encodings_are_interoperable(name):
    data, password, _, expected = fixture("argon2id-chacha.kdbx")
    result = codec.load(data, password, (FIXTURES / name).read_bytes())
    assert fields(result["entries"]) == fields(expected["entries"])


@pytest.mark.parametrize(
    "damage", ["password", "header", "ciphertext", "end", "trailing", "key-file"]
)
def test_authentication_failures_do_not_reach_xml_or_expose_passwords(damage, monkeypatch):
    data, password, key_file, _ = fixture("argon2id-chacha.kdbx")
    if damage == "password":
        password = "incorrect-synthetic-secret"
    elif damage == "key-file":
        key_file = b"incorrect synthetic key component"
    elif damage == "trailing":
        data += b"unexpected"
    else:
        position = {"header": 20, "ciphertext": -80, "end": -10}[damage]
        altered = bytearray(data)
        altered[position] ^= 1
        data = bytes(altered)

    def unexpected_xml(*args, **kwargs):
        pytest.fail("Unauthenticated data reached the XML parser")

    monkeypatch.setattr(codec, "_extract", unexpected_xml)
    with pytest.raises(ServiceError) as rejected:
        codec.load(data, password, key_file)
    assert rejected.value.status == 422
    assert password not in str(rejected.value)


def test_untrusted_kdf_cost_is_rejected_before_any_expensive_hash(monkeypatch):
    data, password, _, _ = fixture()
    altered = bytearray(data)
    marker = b"\x05\x01\x00\x00\x00M\x08\x00\x00\x00"
    position = data.index(marker) + len(marker)
    altered[position : position + 8] = struct.pack("<Q", 1024**3)
    end = 12
    while True:
        kind, size = altered[end], struct.unpack_from("<I", altered, end + 1)[0]
        end += 5 + size
        if not kind:
            break
    altered[end : end + 32] = hashlib.sha256(altered[:end]).digest()
    monkeypatch.setattr(
        codec, "hash_secret_raw", lambda *args, **kwargs: pytest.fail("Unbounded KDF executed")
    )
    with pytest.raises(ServiceError) as refused:
        codec.load(bytes(altered), password)
    assert refused.value.code == "keepass_unsupported" and "64 MiB" in str(refused.value)


def test_bounded_compression_and_xml_refuse_bombs_or_external_entities():
    import gzip

    with pytest.raises(ServiceError):
        codec._inflate(gzip.compress(b"x" * (codec.MAX_PAYLOAD + 1)))
    inner = (
        codec._field(1, struct.pack("<I", 3)) + codec._field(2, bytes(64)) + codec._field(0, b"")
    )
    from defusedxml.common import DefusedXmlException

    with pytest.raises(DefusedXmlException):
        codec._extract(
            inner
            + b'<!DOCTYPE KeePassFile [<!ENTITY x SYSTEM "file:///private">]><KeePassFile>&x;</KeePassFile>'
        )


def test_mixed_exports_cannot_silently_exceed_the_supported_group_depth():
    entry = {
        "id": str(uuid4()),
        "groups": [{"id": str(uuid4()), "name": f"Level {level}"} for level in range(25)],
        "fields": [{"kind": "string", "name": "Password", "value": "synthetic-only"}],
    }
    data = codec.dump([entry], EXPORT_PASSWORD)
    assert codec.load(data, EXPORT_PASSWORD)["entries"][0]["groups"][-1]["name"] == "Level 24"
    other = {**entry, "id": str(uuid4()), "groups": []}
    with pytest.raises(ServiceError) as refused:
        codec.dump([entry, other], EXPORT_PASSWORD)
    assert refused.value.code == "keepass_unsupported" and "separately" in str(refused.value)


def test_import_is_masked_atomic_retryable_and_never_enters_memory(env, vault):
    command = source()
    preview = keepass_vault.preview(vault, env.owner, command)
    assert preview["credentials"] == 11 and preview["entries"] == 2 and preview["can_import"]
    assert vault.list(env.owner)["items"] == []
    assert all(name.startswith("keepass/g-") for name in preview["names"])
    assert not any(
        part in json.dumps(preview)
        for part in ("Synthetic account", "Private team", "plugin-metadata")
    )
    imported, approved = approve(vault, env.owner, command)
    repeated = keepass_vault.import_file(vault, env.owner, approved)
    assert repeated["already_imported"] and repeated["items"] == imported["items"]
    values = []
    for item in imported["items"]:
        identifier = UUID(item["id"])
        values.append(vault.get(env.owner, identifier)["value"])
        assert {g["subject_id"] for g in vault.grants(env.owner, identifier)["items"]} == {
            str(env.owner.key_id)
        }
    assert "synthetic-test-value-α" in values and "synthetic-old-value" not in values
    with psycopg.connect(env.admin_dsn, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT * FROM mnemion.vault_entries WHERE tenant_id=%s", (env.owner.tenant_id,)
        ).fetchall()
        for row in rows:
            assert row["keepass_nonce"] is not None and row["keepass_ciphertext"] is not None
            stored = json.dumps(row, default=str)
            assert all(
                value not in stored
                for value in (
                    "Private team",
                    "Synthetic account",
                    "synthetic-test-value",
                    "synthetic-plugin-value",
                )
            )
        for table in (
            "memories",
            "memory_revisions",
            "sources",
            "source_revisions",
            "embeddings",
            "jobs",
            "core_blocks",
        ):
            assert (
                conn.execute(
                    f"SELECT count(*) AS total FROM mnemion.{table} WHERE tenant_id=%s",
                    (env.owner.tenant_id,),
                ).fetchone()["total"]
                == 0
            )
    audit = vault.audit_events(env.owner)
    assert all(value not in json.dumps(audit) for value in values)
    assert {"keepass_import", "keepass_preview"} <= {event["action"] for event in audit["items"]}


def test_changed_preview_conflicting_names_and_failed_middle_import_write_nothing(
    env, vault, monkeypatch
):
    command = source()
    reviewed = keepass_vault.preview(vault, env.owner, command)
    changed = KeepassImportInput(
        **command.model_dump(exclude={"namespace"}),
        namespace="different",
        expected_plan=reviewed["plan"],
        import_current_values=True,
    )
    with pytest.raises(ServiceError) as refused:
        keepass_vault.import_file(vault, env.owner, changed)
    assert refused.value.code == "keepass_plan_changed" and not vault.list(env.owner)["items"]
    original = vault._set_keepass
    count = 0

    def failed_mapping(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise ServiceError(503, "fixture_failure", "Synthetic interrupted import")
        return original(*args)

    with monkeypatch.context() as patch:
        patch.setattr(vault, "_set_keepass", failed_mapping)
        with pytest.raises(ServiceError):
            approve(vault, env.owner)
    assert vault.list(env.owner)["items"] == []
    create(vault, env.owner, name=reviewed["names"][-1])
    assert not keepass_vault.preview(vault, env.owner, command)["can_import"]
    with pytest.raises(ServiceError) as refused:
        approve(vault, env.owner)
    assert (
        refused.value.code == "keepass_import_conflict" and len(vault.list(env.owner)["items"]) == 1
    )


def test_export_preserves_fields_edited_values_and_group_paths_without_plaintext_files(
    env, vault, monkeypatch
):
    imported, approved = approve(vault, env.owner)
    expected = MANIFEST["fixtures"]["argon2d-aes.kdbx"]["entries"]
    first = next(item for item in imported["items"] if item["name"].endswith("/password"))
    original_id = None
    with env.db.transaction(env.owner) as conn:
        row = vault._entry(conn, UUID(first["id"]), encrypted=True)
        original_id = vault._keepass_mapping(row)["entry_id"]
    updated = vault.put(
        env.owner,
        UUID(first["id"]),
        VaultPut(expected_version=1, name=first["name"], value="updated-synthetic-value"),
    )
    assert updated["version"] == 2
    with pytest.raises(ServiceError) as refused:
        keepass_vault.import_file(vault, env.owner, approved)
    assert refused.value.code == "keepass_import_conflict"

    # Imports/exports must not make a decrypted temporary file through either API.
    def no_files(*args, **kwargs):
        pytest.fail("Credential conversion attempted filesystem access")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", no_files)
        patch.setattr(Path, "open", no_files)
        result = export(vault, env.owner, imported["items"])
    expected_fields = fields(expected)
    expected_fields[(original_id, "string", "Password")] = "updated-synthetic-value"
    assert fields(result["entries"]) == expected_fields
    assert [[group["name"] for group in e["groups"]] for e in result["entries"]] == [
        [group["name"] for group in e["groups"]] for e in expected
    ]


def test_export_enforces_grants_and_never_recovers_an_unselected_title(env, vault):
    imported, _ = approve(vault, env.owner)
    entry = next(item for item in imported["items"] if item["name"].endswith("/password"))
    reader, _ = member(env)
    admin, _ = member(env, administrator=True, kind="human")
    with pytest.raises(ServiceError) as refused:
        keepass_vault.preview(vault, reader, source())
    assert refused.value.status == 403
    with pytest.raises(ServiceError) as refused:
        export(vault, admin, [entry])
    assert refused.value.status == 403
    allow(vault, env.owner, entry, reader, read=True)
    result = export(vault, reader, [entry])
    assert "Synthetic account" not in json.dumps(result)
    assert not any(field["name"] == "UserName" for field in result["entries"][0]["fields"])
    assert next(
        field["value"] for field in result["entries"][0]["fields"] if field["name"] == "Title"
    ).startswith("Mnemion credential ")
    allow(vault, env.owner, entry, reader, remove=True)
    with pytest.raises(ServiceError):
        export(vault, reader, [entry])


def test_native_portable_archive_preserves_encrypted_mapping_with_fresh_grants(env, vault):
    imported, _ = approve(vault, env.owner)
    key = new_vault_key()
    envelope = vault.export(
        env.owner, VaultExport(entry_ids=[i["id"] for i in imported["items"]], recovery_key=key)
    )
    document = VaultCipher(key).open_archive(envelope)
    assert document["version"] == 2 and all("keepass" in i for i in document["entries"])
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Restored fixture",
        administrator_name="Fresh owner",
        generation=env.embedder.generation,
    )
    owner = env.db.authenticate(other["api_key"])
    restored = vault.import_archive(owner, VaultImport(archive=envelope, recovery_key=key))
    assert not {i["id"] for i in imported["items"]} & {i["id"] for i in restored["items"]}
    result = export(vault, owner, restored["items"])
    assert fields(result["entries"]) == fields(MANIFEST["fixtures"]["argon2d-aes.kdbx"]["entries"])
    assert all(
        vault.grants(owner, UUID(i["id"]))["items"][0]["subject_id"] == str(owner.key_id)
        for i in restored["items"]
    )


def test_mapping_substitution_deletion_and_recovery_do_not_reveal_old_context(env, vault):
    from mnemion.service.recovery import _ledger
    from mnemion.service.vault_recovery import restore

    imported, approved = approve(vault, env.owner)
    first = imported["items"][0]
    with env.db.transaction(env.owner) as conn:
        old = vault._entry(conn, UUID(first["id"]), encrypted=True)
        other = vault._entry(conn, UUID(imported["items"][1]["id"]), encrypted=True)
    forged = {
        **other,
        "keepass_nonce": old["keepass_nonce"],
        "keepass_ciphertext": old["keepass_ciphertext"],
    }
    with pytest.raises(ServiceError) as invalid:
        vault._keepass_mapping(forged)
    assert invalid.value.code == "vault_integrity"
    vault.delete(env.owner, UUID(first["id"]), VaultDelete(expected_version=1))
    with pytest.raises(ServiceError):
        keepass_vault.import_file(vault, env.owner, approved)
    with psycopg.connect(env.admin_dsn, row_factory=dict_row) as conn:
        columns = "nonce,ciphertext,keepass_nonce,keepass_ciphertext"
        cleared = conn.execute(
            f"SELECT {columns} FROM mnemion.vault_entries WHERE id=%s", (first["id"],)
        ).fetchone()
        assert all(value is None for value in cleared.values())
        ledger = _ledger(conn)
        conn.execute("DELETE FROM mnemion.vault_denials WHERE entry_id=%s", (first["id"],))
        conn.execute(
            "UPDATE mnemion.vault_entries SET deleted_at=NULL,version=1,nonce=%s,ciphertext=%s,keepass_nonce=%s,keepass_ciphertext=%s WHERE id=%s",
            (*[old[c] for c in columns.split(",")], first["id"]),
        )
        restore(conn, ledger)
        assert all(
            value is None
            for value in conn.execute(
                f"SELECT {columns} FROM mnemion.vault_entries WHERE id=%s", (first["id"],)
            )
            .fetchone()
            .values()
        )


def test_http_sdk_and_private_agent_transport_preserve_secret_boundaries(
    env, vault, tmp_path, monkeypatch, capsys
):
    app = create_app(
        env.db, env.embedder, vault_settings=vault.settings, studio_enabled=False, mcp_enabled=False
    )
    command = source()
    with TestClient(app) as api:
        response = api.post(
            "/v1/vault/keepass/preview",
            headers=authorization(env.token),
            json={"file": "invalid", "password": "never-echo-this-synthetic-password"},
        )
        assert response.status_code == 422 and "never-echo" not in response.text
        assert response.headers["cache-control"] == "no-store"
    with running(app) as url, Client(url, env.token) as client:
        preview = client.vault_keepass_preview(command)
        imported = client.vault_keepass_import(
            KeepassImportInput(
                **command.model_dump(), expected_plan=preview.plan, import_current_values=True
            )
        )
        assert len(imported.items) == preview.credentials == 11
        result = client.vault_keepass_export(
            KeepassExportInput(
                entry_ids=[item.id for item in imported.items], password=EXPORT_PASSWORD
            )
        )
        assert fields(
            codec.load(base64.b64decode(result.file), EXPORT_PASSWORD)["entries"]
        ) == fields(MANIFEST["fixtures"]["argon2d-aes.kdbx"]["entries"])
        monkeypatch.setenv("MNEMION_API_URL", url)
        monkeypatch.setenv("MNEMION_API_KEY", env.token)
        request, output = tmp_path / "request.json", tmp_path / "result.json"
        body = {
            "body": {
                "entry_ids": [str(item.id) for item in imported.items],
                "password": EXPORT_PASSWORD,
            }
        }
        with private_output(request) as stream:
            stream.write(json.dumps(body).encode())
        assert control_cli.main(["call", "vault.keepass.export", "--input", str(request)]) == 1
        assert not output.exists()
        assert (
            control_cli.main(
                [
                    "call",
                    "vault.keepass.export",
                    "--input",
                    str(request),
                    "--result-file",
                    str(output),
                ]
            )
            == 0
        )
        assert json.loads(output.read_text())["entries"] == 2
        printed = capsys.readouterr().out
        assert EXPORT_PASSWORD not in printed and result.file not in printed
    for action in ("preview", "import", "export"):
        described = agent_control.describe("vault.keepass." + action)
        assert described["sensitive_input"] and described["sensitive_result"]
