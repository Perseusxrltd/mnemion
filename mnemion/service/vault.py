"""Explicit, audited secret access with no memory or source service dependency."""

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from .db import Database, Identity, require_administrator
from .errors import ServiceError, forbidden, not_found
from .models import json_value
from .vault_crypto import VaultCipher, VaultSettings
from .vault_models import (
    KeepassMapping,
    VaultArchive,
    VaultAuditorChange,
    VaultDelete,
    VaultExport,
    VaultGrant,
    VaultImport,
    VaultPut,
)

METADATA = "id,name,version,access_version,created_at,updated_at"


class VaultService:
    def __init__(self, database: Database, settings: VaultSettings):
        self.db, self.settings = database, settings
        self.cipher = None
        self.invalid_key = False
        if settings.key:
            try:
                self.cipher = VaultCipher(settings.key.get_secret_value())
            except ValueError:
                # A damaged vault configuration must not stop memory access.
                self.invalid_key = True

    @staticmethod
    def _scope(conn, identity):
        conn.execute("SELECT set_config('mnemion.vault_key_id',%s,true)", (str(identity.key_id),))

    @staticmethod
    def _administrator(conn):
        return conn.execute("SELECT mnemion.administrator() AS value").fetchone()["value"]

    @staticmethod
    def _auditor(conn):
        return conn.execute("SELECT mnemion.vault_auditor() AS value").fetchone()["value"]

    @staticmethod
    def _person(conn, identity):
        row = conn.execute(
            """SELECT p.id FROM mnemion.principals p WHERE p.id=%s AND p.kind='human'
               AND EXISTS (SELECT FROM mnemion.sign_in_sessions s
                   WHERE s.tenant_id=p.tenant_id AND s.key_id=%s)""",
            (identity.principal_id, identity.key_id),
        ).fetchone()
        return row["id"] if row else None

    def _status(self, conn, identity):
        required = [
            row["key_id"]
            for row in conn.execute(
                "SELECT DISTINCT key_id FROM mnemion.vault_entries WHERE deleted_at IS NULL ORDER BY key_id LIMIT 9"
            )
        ]
        key_id = self.cipher.key_id if self.cipher else None
        code = (
            "vault_disabled"
            if not self.settings.enabled
            else "vault_key_invalid"
            if self.invalid_key
            else "vault_key_missing"
            if not self.cipher
            else "vault_key_unavailable"
            if any(value != key_id for value in required)
            else None
        )
        return {
            "configured": bool(self.settings.key),
            "enabled": self.settings.enabled,
            "mcp_enabled": self.settings.enabled and self.settings.mcp_enabled,
            "mcp_metadata_enabled": self.settings.enabled
            and (self.settings.mcp_metadata_enabled or self.settings.mcp_enabled),
            "metadata_available": self.settings.enabled,
            "audit_access": self._administrator(conn)
            or (self.settings.enabled and self._auditor(conn)),
            "available": code is None,
            "error_code": code,
            "key_id": key_id,
            "required_key_ids": required,
            "current_key_id": str(identity.key_id),
            "current_person_id": str(person) if (person := self._person(conn, identity)) else None,
            "administrator": self._administrator(conn),
        }

    def status(self, identity: Identity):
        with self.db.transaction(identity) as conn:
            self._scope(conn, identity)
            return self._status(conn, identity)

    @contextmanager
    def _access(self, identity, action, entry=None, *, metadata=False, target_key=None):
        failure = None
        # This is also the key/person/grant retirement lock. Values are never
        # released by a request that waited behind its own revocation.
        with self.db.administration_transaction(identity) as conn:
            self._scope(conn, identity)
            try:
                with conn.transaction():
                    status = (
                        {"available": self.settings.enabled, "error_code": "vault_disabled"}
                        if metadata
                        else self._status(conn, identity)
                    )
                    if not status["available"]:
                        raise ServiceError(
                            503,
                            status["error_code"],
                            "The vault is unavailable. Its host operator must enable it and restore the matching encryption key.",
                        )
                    yield conn
            except ServiceError as error:
                failure = error
            outcome = (
                "allowed"
                if failure is None
                else "conflict"
                if failure.status == 409
                else "unavailable"
                if failure.status == 503
                else "invalid"
                if failure.status == 422
                else "denied"
            )
            # An audit failure rolls back the whole operation. Neither value,
            # label, ciphertext, request body nor recovery key belongs here.
            conn.execute(
                """INSERT INTO mnemion.vault_audit_events
                   (tenant_id,id,principal_id,key_id,entry_id,action,outcome,target_key_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    identity.tenant_id,
                    uuid4(),
                    identity.principal_id,
                    identity.key_id,
                    entry,
                    action,
                    outcome,
                    target_key,
                ),
            )
        if failure is not None:
            raise failure

    @staticmethod
    def _entry(conn, entry, *, encrypted=False):
        columns = "*" if encrypted else METADATA
        row = conn.execute(
            f"SELECT {columns},mnemion.vault_rights(id) AS rights FROM mnemion.vault_entries "
            "WHERE id=%s AND deleted_at IS NULL",
            (entry,),
        ).fetchone()
        if not row:
            raise not_found()
        return row

    @staticmethod
    def _metadata(row, *, administrator):
        return {
            **json_value({key: row[key] for key in METADATA.split(",")}),
            "permissions": {
                "read": bool(row["rights"] & 2),
                "write": bool(row["rights"] & 4),
                "manage": administrator,
            },
        }

    def list(self, identity: Identity, *, offset=0, limit=100):
        with self._access(identity, "list", metadata=True) as conn:
            admin = self._administrator(conn)
            rows = conn.execute(
                f"SELECT {METADATA},mnemion.vault_rights(id) AS rights FROM mnemion.vault_entries "
                "WHERE deleted_at IS NULL ORDER BY name,id LIMIT %s OFFSET %s",
                (limit + 1, offset),
            ).fetchall()
            return {
                "items": [self._metadata(row, administrator=admin) for row in rows[:limit]],
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def get(self, identity: Identity, entry: UUID):
        with self._access(identity, "get", entry) as conn:
            row = self._entry(conn, entry, encrypted=True)
            if not row["rights"] & 2:
                raise forbidden()
            return {
                **self._metadata(row, administrator=self._administrator(conn)),
                "value": self.cipher.decrypt(row),
            }

    @staticmethod
    def _collision(conn, name, entry):
        if conn.execute(
            "SELECT id FROM mnemion.vault_entries WHERE name=%s AND id<>%s AND deleted_at IS NULL",
            (name, entry),
        ).fetchone():
            raise ServiceError(
                409,
                "vault_name_exists",
                "Choose a different credential name; existing values are not overwritten.",
            )

    def _put(self, conn, identity, entry, command):
        admin = self._administrator(conn)
        row = conn.execute(
            "SELECT *,mnemion.vault_rights(id) AS rights FROM mnemion.vault_entries WHERE id=%s",
            (entry,),
        ).fetchone()
        if command.expected_version == 0:
            require_administrator(conn)
            if (
                row
                or conn.execute(
                    "SELECT 1 AS present FROM mnemion.vault_denials WHERE entry_id=%s", (entry,)
                ).fetchone()
            ):
                raise ServiceError(
                    409,
                    "vault_entry_exists",
                    "This credential identifier has already been used. Inspect the current list before retrying.",
                )
            if (
                conn.execute(
                    "SELECT count(*) AS count FROM mnemion.vault_entries WHERE deleted_at IS NULL"
                ).fetchone()["count"]
                >= 10000
            ):
                raise ServiceError(
                    409, "vault_capacity", "This workspace already has 10000 credentials."
                )
        else:
            if not row or row["deleted_at"] is not None:
                raise not_found()
            if not row["rights"] & 4:
                raise forbidden()
            if row["version"] != command.expected_version:
                raise ServiceError(
                    409,
                    "vault_entry_changed",
                    "The credential changed. Reload its current version before saving.",
                )
            if not admin and command.name != row["name"]:
                raise ServiceError(
                    403, "vault_rename_forbidden", "Only an administrator can rename a credential."
                )
        self._collision(conn, command.name, entry)
        version = command.expected_version + 1
        nonce, ciphertext = self.cipher.encrypt(
            identity.tenant_id, entry, command.name, version, command.value.get_secret_value()
        )
        if row is None:
            conn.execute(
                """INSERT INTO mnemion.vault_entries
                   (tenant_id,id,name,version,key_id,nonce,ciphertext,created_by,updated_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    identity.tenant_id,
                    entry,
                    command.name,
                    version,
                    self.cipher.key_id,
                    nonce,
                    ciphertext,
                    identity.principal_id,
                    identity.principal_id,
                ),
            )
            person = self._person(conn, identity)
            conn.execute(
                """INSERT INTO mnemion.vault_grants(tenant_id,entry_id,subject_kind,subject_id,permissions)
                   VALUES (%s,%s,%s,%s,7)""",
                (
                    identity.tenant_id,
                    entry,
                    "person" if person else "key",
                    person or identity.key_id,
                ),
            )
        else:
            conn.execute(
                """UPDATE mnemion.vault_entries SET name=%s,version=%s,key_id=%s,nonce=%s,ciphertext=%s,
                   updated_by=%s,updated_at=clock_timestamp() WHERE id=%s""",
                (
                    command.name,
                    version,
                    self.cipher.key_id,
                    nonce,
                    ciphertext,
                    identity.principal_id,
                    entry,
                ),
            )
        return self._metadata(self._entry(conn, entry), administrator=admin)

    def put(self, identity: Identity, entry: UUID, command: VaultPut):
        with self._access(identity, "put", entry) as conn:
            return self._put(conn, identity, entry, command)

    def _set_keepass(self, conn, identity, entry, mapping):
        model = KeepassMapping.model_validate(mapping)
        nonce, ciphertext = self.cipher.encrypt_keepass(
            identity.tenant_id, entry, model.model_dump(mode="json")
        )
        conn.execute(
            "UPDATE mnemion.vault_entries SET keepass_nonce=%s,keepass_ciphertext=%s WHERE id=%s",
            (nonce, ciphertext, entry),
        )

    def _keepass_mapping(self, row):
        mapping = self.cipher.decrypt_keepass(row)
        if mapping is None:
            return None
        try:
            return KeepassMapping.model_validate(mapping).model_dump(mode="json")
        except ValidationError:
            raise ServiceError(
                503, "vault_integrity", "The encrypted KeePass mapping could not be verified."
            ) from None

    @staticmethod
    def _grants(conn, entry):
        row = VaultService._entry(conn, entry)
        values = conn.execute(
            """SELECT g.subject_kind,g.subject_id,(g.permissions&2)=2 AS read,(g.permissions&4)=4 AS write,
                 coalesce(p.name,k.name,'Unavailable identity') AS name,
                 CASE WHEN g.subject_kind='person' THEN p.disabled_at IS NULL AND p.id IS NOT NULL
                   ELSE k.id IS NOT NULL AND k.revoked_at IS NULL AND kp.disabled_at IS NULL
                     AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp()) END AS active
               FROM mnemion.vault_grants g
               LEFT JOIN mnemion.principals p ON g.subject_kind='person' AND p.tenant_id=g.tenant_id AND p.id=g.subject_id
               LEFT JOIN mnemion.api_keys k ON g.subject_kind='key' AND k.tenant_id=g.tenant_id AND k.id=g.subject_id
               LEFT JOIN mnemion.principals kp ON kp.tenant_id=k.tenant_id AND kp.id=k.principal_id
               WHERE g.entry_id=%s ORDER BY g.subject_kind,g.subject_id LIMIT 1000""",
            (entry,),
        ).fetchall()
        return {
            "entry_id": str(entry),
            "access_version": row["access_version"],
            "items": json_value(values),
        }

    def grants(self, identity: Identity, entry: UUID):
        with self._access(identity, "list", entry, metadata=True) as conn:
            require_administrator(conn)
            return self._grants(conn, entry)

    @staticmethod
    def _auditors(conn, *, offset=0, limit=100, key=None):
        return conn.execute(
            """SELECT a.key_id,k.principal_id,k.name,a.version,a.enabled,a.expires_at,
                a.created_at,a.updated_at,
                (a.enabled AND (a.expires_at IS NULL OR a.expires_at>clock_timestamp())
                  AND k.revoked_at IS NULL AND p.disabled_at IS NULL
                  AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())) AS active
               FROM mnemion.vault_auditors a
               JOIN mnemion.api_keys k ON k.tenant_id=a.tenant_id AND k.id=a.key_id
               JOIN mnemion.principals p ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
               WHERE (%s::uuid IS NULL OR a.key_id=%s) ORDER BY a.key_id LIMIT %s OFFSET %s""",
            (key, key, limit, offset),
        ).fetchall()

    def auditors(self, identity: Identity, *, offset=0, limit=100, key_id=None):
        with self._access(identity, "list", metadata=True) as conn:
            require_administrator(conn)
            rows = self._auditors(conn, offset=offset, limit=limit + 1, key=key_id)
            return {
                "items": json_value(rows[:limit]),
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def auditor(self, identity: Identity, key: UUID, command: VaultAuditorChange):
        with self._access(identity, "auditor", metadata=True, target_key=key) as conn:
            require_administrator(conn)
            rows = self._auditors(conn, key=key)
            current = rows[0] if rows else None
            if (current["version"] if current else 0) != command.expected_version:
                raise ServiceError(
                    409, "vault_auditor_changed", "Auditor access changed. Reload and review it."
                )
            if not conn.execute(
                """SELECT k.id FROM mnemion.api_keys k JOIN mnemion.principals p
                   ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
                   WHERE k.id=%s AND (NOT %s OR (k.revoked_at IS NULL
                     AND p.disabled_at IS NULL
                     AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())))""",
                (key, command.enabled),
            ).fetchone():
                raise ServiceError(
                    422, "vault_grant_subject", "Choose an active key in this workspace."
                )
            if (
                command.enabled
                and command.expires_at
                and not conn.execute(
                    "SELECT %s::timestamptz>clock_timestamp() AS valid", (command.expires_at,)
                ).fetchone()["valid"]
            ):
                raise ServiceError(
                    422, "vault_auditor_expiry", "Choose a future expiry for this grant."
                )
            if (
                current is None
                and conn.execute("SELECT count(*) AS count FROM mnemion.vault_auditors").fetchone()[
                    "count"
                ]
                >= 1000
            ):
                raise ServiceError(
                    409, "vault_grant_capacity", "This vault already has 1000 auditor records."
                )
            conn.execute(
                """INSERT INTO mnemion.vault_auditors(tenant_id,key_id,version,enabled,expires_at)
                   VALUES (%s,%s,1,%s,%s) ON CONFLICT(tenant_id,key_id) DO UPDATE SET
                   version=vault_auditors.version+1,enabled=excluded.enabled,
                   expires_at=excluded.expires_at,updated_at=clock_timestamp()""",
                (identity.tenant_id, key, command.enabled, command.expires_at),
            )
            return json_value(self._auditors(conn, key=key)[0])

    def grant(self, identity: Identity, entry: UUID, command: VaultGrant):
        with self._access(identity, "grant", entry) as conn:
            require_administrator(conn)
            row = self._entry(conn, entry)
            if row["access_version"] != command.expected_access_version:
                raise ServiceError(
                    409,
                    "vault_access_changed",
                    "Credential access changed. Reload and review the current grants.",
                )
            if command.remove:
                conn.execute(
                    "DELETE FROM mnemion.vault_grants WHERE entry_id=%s AND subject_kind=%s AND subject_id=%s",
                    (entry, command.subject_kind, command.subject_id),
                )
            else:
                query = (
                    "SELECT id FROM mnemion.principals WHERE id=%s AND kind='human' AND disabled_at IS NULL"
                    if command.subject_kind == "person"
                    else "SELECT k.id FROM mnemion.api_keys k JOIN mnemion.principals p ON p.tenant_id=k.tenant_id AND p.id=k.principal_id "
                    "WHERE k.id=%s AND k.revoked_at IS NULL AND p.disabled_at IS NULL "
                    "AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())"
                )
                if not conn.execute(query, (command.subject_id,)).fetchone():
                    raise ServiceError(
                        422,
                        "vault_grant_subject",
                        "Choose an active person or key in this workspace.",
                    )
                exists = conn.execute(
                    "SELECT 1 AS present FROM mnemion.vault_grants WHERE entry_id=%s AND subject_kind=%s AND subject_id=%s",
                    (entry, command.subject_kind, command.subject_id),
                ).fetchone()
                if (
                    not exists
                    and conn.execute(
                        "SELECT count(*) AS count FROM mnemion.vault_grants WHERE entry_id=%s",
                        (entry,),
                    ).fetchone()["count"]
                    >= 1000
                ):
                    raise ServiceError(
                        409, "vault_grant_capacity", "This credential already has 1000 grants."
                    )
                conn.execute(
                    """INSERT INTO mnemion.vault_grants(tenant_id,entry_id,subject_kind,subject_id,permissions)
                       VALUES (%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,entry_id,subject_kind,subject_id)
                       DO UPDATE SET permissions=excluded.permissions""",
                    (
                        identity.tenant_id,
                        entry,
                        command.subject_kind,
                        command.subject_id,
                        1 | (2 if command.read else 0) | (4 if command.write else 0),
                    ),
                )
            conn.execute(
                "UPDATE mnemion.vault_entries SET access_version=access_version+1 WHERE id=%s",
                (entry,),
            )
            return self._grants(conn, entry)

    def delete(self, identity: Identity, entry: UUID, command: VaultDelete):
        with self._access(identity, "delete", entry) as conn:
            require_administrator(conn)
            row = self._entry(conn, entry)
            if row["version"] != command.expected_version:
                raise ServiceError(
                    409, "vault_entry_changed", "The credential changed. Reload before deleting it."
                )
            conn.execute(
                "INSERT INTO mnemion.vault_denials(tenant_id,entry_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (identity.tenant_id, entry),
            )
            conn.execute("DELETE FROM mnemion.vault_grants WHERE entry_id=%s", (entry,))
            conn.execute(
                """UPDATE mnemion.vault_entries SET deleted_at=clock_timestamp(),updated_at=clock_timestamp(),
                         version=version+1,updated_by=%s,nonce=NULL,ciphertext=NULL,
                         keepass_nonce=NULL,keepass_ciphertext=NULL WHERE id=%s""",
                (identity.principal_id, entry),
            )
            return {"id": str(entry), "deleted": True}

    def export(self, identity: Identity, command: VaultExport):
        with self._access(identity, "export") as conn:
            contents = []
            for entry in command.entry_ids:
                row = self._entry(conn, entry, encrypted=True)
                if not row["rights"] & 2:
                    raise forbidden()
                item = {"name": row["name"], "value": self.cipher.decrypt(row)}
                if mapping := self._keepass_mapping(row):
                    item["keepass"] = mapping
                contents.append(item)
            envelope = VaultCipher(command.recovery_key.get_secret_value()).seal_archive(
                {
                    "format": "mnemion-vault-contents",
                    "version": 2 if any("keepass" in item for item in contents) else 1,
                    "source_tenant_id": str(identity.tenant_id),
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "entries": contents,
                }
            )
            # Individual reads remain attributable even for a multi-secret export.
            for entry in command.entry_ids:
                conn.execute(
                    """INSERT INTO mnemion.vault_audit_events
                    (tenant_id,id,principal_id,key_id,entry_id,action,outcome)
                    VALUES (%s,%s,%s,%s,%s,'export','allowed')""",
                    (identity.tenant_id, uuid4(), identity.principal_id, identity.key_id, entry),
                )
            return envelope

    def import_archive(self, identity: Identity, command: VaultImport):
        with self._access(identity, "import") as conn:
            require_administrator(conn)
            document = VaultCipher(command.recovery_key.get_secret_value()).open_archive(
                command.archive.model_dump()
            )
            try:
                archive = VaultArchive.model_validate(document)
            except ValidationError:
                raise ServiceError(
                    422,
                    "vault_archive_invalid",
                    "The decrypted export does not match the supported vault format.",
                ) from None
            if len({entry.name for entry in archive.entries}) != len(archive.entries):
                raise ServiceError(
                    422, "vault_archive_invalid", "The export contains duplicate credential names."
                )
            items = []
            # Rebase imported mapping batches so separate restores cannot merge
            # different credentials merely because their original file matched.
            batches = {}
            for entry in archive.entries:
                identifier = uuid4()
                items.append(
                    self._put(
                        conn,
                        identity,
                        identifier,
                        VaultPut(expected_version=0, name=entry.name, value=entry.value),
                    )
                )
                if entry.keepass:
                    if archive.version != 2:
                        raise ServiceError(
                            422,
                            "vault_archive_invalid",
                            "KeePass mappings require the version 2 vault contents format.",
                        )
                    mapping = entry.keepass.model_dump(mode="json")
                    mapping["batch_id"] = str(batches.setdefault(mapping["batch_id"], uuid4()))
                    self._set_keepass(conn, identity, identifier, mapping)
            return {"items": items, "next_offset": None}

    def audit_events(self, identity: Identity, *, offset=0, limit=100):
        with self.db.administration_transaction(identity) as conn:
            self._scope(conn, identity)
            if not self._administrator(conn) and not (
                self.settings.enabled and self._auditor(conn)
            ):
                raise forbidden()
            rows = conn.execute(
                """SELECT id,principal_id,key_id,entry_id,action,outcome,occurred_at,target_key_id
                FROM mnemion.vault_audit_events ORDER BY occurred_at DESC,id LIMIT %s OFFSET %s""",
                (limit + 1, offset),
            ).fetchall()
            return {
                "items": json_value(rows[:limit]),
                "next_offset": offset + limit if len(rows) > limit else None,
            }
