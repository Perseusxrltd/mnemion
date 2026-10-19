"""Explicit, audited KDBX transport, separate from every memory/source pipeline."""

import base64
import hashlib
from urllib.parse import quote
from uuid import uuid4, uuid5

from pydantic import ValidationError

from . import keepass_codec as codec
from .db import require_administrator
from .errors import ServiceError, forbidden
from .vault_crypto import canonical
from .vault_models import KeepassMapping, VaultPut


def _plan(identity, command):
    try:
        data = base64.b64decode(command.file.get_secret_value(), validate=True)
        keyfile = (
            base64.b64decode(command.key_file.get_secret_value(), validate=True)
            if command.key_file
            else None
        )
    except ValueError:
        raise codec.invalid() from None
    document = codec.load(
        data, command.password.get_secret_value() if command.password is not None else None, keyfile
    )
    digest = hashlib.sha256(
        canonical(
            {
                "format": "mnemion-keepass-import",
                "version": 1,
                "file": hashlib.sha256(data).hexdigest(),
                "namespace": command.namespace,
                "mask_names": command.mask_names,
                "tenant": str(identity.tenant_id),
                "principal": str(identity.principal_id),
            }
        )
    ).hexdigest()
    batch = uuid5(identity.tenant_id, digest)
    items, all_names, empty_count = [], set(), 0
    for entry in document["entries"]:
        empty = [
            {"kind": field["kind"], "name": field["name"]}
            for field in entry["fields"]
            if field["value"] == ""
        ]
        empty_count += len(empty)
        for field in entry["fields"]:
            if field["value"] == "":
                continue
            if command.mask_names:
                group = "g-" + hashlib.sha256(canonical(entry["groups"])).hexdigest()[:16]
                title = "e-" + entry["id"].replace("-", "")[:20]
                label = (
                    field["name"].lower()
                    if field["kind"] == "string"
                    and field["name"] in {"Title", "UserName", "Password", "URL", "Notes"}
                    else "field-"
                    + hashlib.sha256(
                        canonical([str(batch), field["kind"], field["name"]])
                    ).hexdigest()[:20]
                )
                name = "/".join((command.namespace, group, title, label))
            else:
                components = [
                    command.namespace,
                    *(group["name"] for group in entry["groups"]),
                    entry["title"] or entry["id"],
                    field["kind"],
                    field["name"],
                ]
                name = "/".join(quote(component, safe="-_.") for component in components)
            mapping = {
                "batch_id": str(batch),
                "entry_id": entry["id"],
                "groups": entry["groups"],
                "field_kind": field["kind"],
                "field_name": field["name"],
                "empty_fields": empty,
            }
            try:
                command_item = VaultPut(expected_version=0, name=name, value=field["value"])
                mapping = KeepassMapping.model_validate(mapping).model_dump(mode="json")
            except ValidationError:
                raise codec.unsupported(
                    "The mapped names or context exceed the transfer limits. Use masked names or a smaller KeePass selection."
                ) from None
            if name in all_names or len(canonical(mapping)) > 32768:
                raise codec.unsupported(
                    "The mapped names repeat or a field's context exceeds 32 KiB. Use a smaller KeePass selection."
                )
            all_names.add(name)
            identifier = uuid5(batch, entry["id"] + "/" + field["kind"] + "/" + field["name"])
            items.append({"id": identifier, "command": command_item, "mapping": mapping})
    return (
        digest,
        items,
        {
            "plan": digest,
            "entries": len(document["entries"]),
            "credentials": len(items),
            "empty_fields": empty_count,
            "names": [item["command"].name for item in items],
            "mask_names": command.mask_names,
            "omitted": document["omitted"],
        },
    )


def _existing(conn, items):
    identifiers = [item["id"] for item in items]
    rows = {
        row["id"]: row
        for row in conn.execute(
            "SELECT id,name,version,deleted_at FROM mnemion.vault_entries WHERE id=ANY(%s)",
            (identifiers,),
        )
    }
    repeated = len(rows) == len(items) and all(
        rows[item["id"]]["version"] == 1
        and rows[item["id"]]["deleted_at"] is None
        and rows[item["id"]]["name"] == item["command"].name
        for item in items
    )
    conflicts = conn.execute(
        """SELECT count(*) AS count FROM mnemion.vault_entries
        WHERE deleted_at IS NULL AND name=ANY(%s) AND NOT id=ANY(%s)""",
        ([item["command"].name for item in items], identifiers),
    ).fetchone()["count"]
    return {
        "already_imported": repeated,
        "can_import": not conflicts and (not rows or repeated),
        "name_conflicts": conflicts,
    }


def preview(service, identity, command):
    with service._access(identity, "keepass_preview") as conn:
        require_administrator(conn)
        with codec.crypto_slot():
            _, items, result = _plan(identity, command)
        return {**result, **_existing(conn, items)}


def import_file(service, identity, command):
    with service._access(identity, "keepass_import") as conn:
        require_administrator(conn)
        with codec.crypto_slot():
            digest, items, _ = _plan(identity, command)
        if digest != command.expected_plan:
            raise ServiceError(
                409,
                "keepass_plan_changed",
                "The file or mapping options changed. Review a fresh preview.",
            )
        existing = _existing(conn, items)
        if not existing["can_import"]:
            raise ServiceError(
                409,
                "keepass_import_conflict",
                "A credential name already exists or a previous import changed. Choose another prefix; existing values are not overwritten.",
            )
        if existing["already_imported"]:
            return {
                "items": [
                    service._metadata(service._entry(conn, item["id"]), administrator=True)
                    for item in items
                ],
                "already_imported": True,
            }
        result = []
        for item in items:
            result.append(service._put(conn, identity, item["id"], item["command"]))
            service._set_keepass(conn, identity, item["id"], item["mapping"])
        return {"items": result, "already_imported": False}


def export_file(service, identity, command):
    with service._access(identity, "keepass_export") as conn:
        entries = {}
        for identifier in command.entry_ids:
            row = service._entry(conn, identifier, encrypted=True)
            if not row["rights"] & 2:
                raise forbidden()
            value = service.cipher.decrypt(row)
            mapping = service._keepass_mapping(row)
            if mapping:
                key = (mapping["batch_id"], mapping["entry_id"])
                entry = entries.setdefault(
                    key, {"id": mapping["entry_id"], "groups": mapping["groups"], "fields": []}
                )
                field = {
                    "kind": mapping["field_kind"],
                    "name": mapping["field_name"],
                    "value": value,
                }
                if any(
                    item["name"] == field["name"]
                    and item["kind"] == field["kind"]
                    and item["value"] != ""
                    for item in entry["fields"]
                ):
                    raise ServiceError(
                        409,
                        "keepass_mapping_conflict",
                        "This selection maps multiple credentials to the same KeePass field. Export them separately.",
                    )
                entry["fields"] = [
                    item
                    for item in entry["fields"]
                    if (item["kind"], item["name"]) != (field["kind"], field["name"])
                ]
                entry["fields"].append(field)
                for empty in mapping["empty_fields"]:
                    if not any(
                        (item["kind"], item["name"]) == (empty["kind"], empty["name"])
                        for item in entry["fields"]
                    ):
                        entry["fields"].append({**empty, "value": ""})
            else:
                entries[(str(identifier), "native")] = {
                    "id": str(identifier),
                    "groups": [],
                    "fields": [
                        {"kind": "string", "name": "Title", "value": row["name"]},
                        {"kind": "string", "name": "Password", "value": value},
                    ],
                }
        for entry in entries.values():
            if not any(
                field["kind"] == "string" and field["name"] == "Title" for field in entry["fields"]
            ):
                entry["fields"].insert(
                    0,
                    {
                        "kind": "string",
                        "name": "Title",
                        "value": "Mnemion credential " + entry["id"][:8],
                    },
                )
        with codec.crypto_slot():
            data = codec.dump(list(entries.values()), command.password.get_secret_value())
        for identifier in command.entry_ids:
            conn.execute(
                """INSERT INTO mnemion.vault_audit_events
                (tenant_id,id,principal_id,key_id,entry_id,action,outcome)
                VALUES (%s,%s,%s,%s,%s,'keepass_export','allowed')""",
                (identity.tenant_id, uuid4(), identity.principal_id, identity.key_id, identifier),
            )
        return {
            "format": "kdbx",
            "version": "4.1",
            "file": base64.b64encode(data).decode(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "credentials": len(command.entry_ids),
            "entries": len(entries),
        }
