"""Bounded KDBX 4 transport using established cryptographic primitives.

Format: https://keepass.info/help/kb/kdbx.html. No filesystem access, external
entities, key-provider plugins or unauthenticated decryption are supported.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
import struct
import threading
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET
import zlib

from argon2.exceptions import HashingError
from argon2.low_level import Type, hash_secret_raw
from Cryptodome.Cipher import AES, ChaCha20, Salsa20
from Cryptodome.Util.Padding import pad, unpad
from defusedxml import ElementTree as SafeXML
from defusedxml.common import DefusedXmlException

from .errors import ServiceError

MAX_FILE = 1_000_000
MAX_PAYLOAD = 2_000_000
MAX_HEADER = 65_536
MAX_KEYFILE = 65_536
MAX_FIELDS = 500
AES_ID = bytes.fromhex("31c1f2e6bf714350be5805216afc5aff")
CHACHA_ID = bytes.fromhex("d6038a2b8b6f4cb5a524339a31dbb59a")
AES_KDF = bytes.fromhex("c9d9f39a628a4460bf740d08c18a4fea")
ARGON_D = bytes.fromhex("ef636ddf8c29444b91f7a9a403e30a0c")
ARGON_ID = bytes.fromhex("9e298b1956db4773b23dfc3ec6f0a1e6")
SIGNATURE = bytes.fromhex("03d9a29a67fb4bb5")
_slot = threading.BoundedSemaphore(1)


def invalid():
    return ServiceError(
        422, "keepass_invalid", "The KDBX file, password or key file could not be verified."
    )


def unsupported(detail):
    return ServiceError(422, "keepass_unsupported", detail)


@contextmanager
def crypto_slot():
    if not _slot.acquire(blocking=False):
        raise ServiceError(
            503, "keepass_busy", "Another KeePass operation is running. Try again shortly."
        )
    try:
        yield
    finally:
        _slot.release()


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def read(self, count):
        if count < 0 or count > len(self.data) - self.pos:
            raise invalid()
        value = self.data[self.pos : self.pos + count]
        self.pos += count
        return value

    def number(self, size):
        return int.from_bytes(self.read(size), "little")

    def field(self):
        return self.number(1), self.read(self.number(4))

    @property
    def remaining(self):
        return len(self.data) - self.pos


def _dictionary(data):
    reader, result = Reader(data), {}
    if reader.number(2) >> 8 != 1:
        raise unsupported("This KDBX parameter dictionary version is not supported.")
    while kind := reader.number(1):
        name = reader.read(reader.number(4)).decode("utf-8")
        value = reader.read(reader.number(4))
        if name in result or len(result) >= 32 or len(name) > 128:
            raise invalid()
        if kind in {4, 5, 12, 13}:
            if len(value) != (4 if kind in {4, 12} else 8):
                raise invalid()
            value = int.from_bytes(value, "little", signed=kind in {12, 13})
        elif kind != 0x42:
            raise unsupported("This KDBX key derivation parameter type is not supported.")
        result[name] = value
    if reader.remaining:
        raise invalid()
    return result


def _encode_dictionary(values):
    data = bytearray(b"\x00\x01")
    for name, (kind, value) in values.items():
        raw = value if kind == 0x42 else value.to_bytes(4 if kind == 4 else 8, "little")
        name = name.encode("utf-8")
        data.extend(
            bytes([kind]) + struct.pack("<I", len(name)) + name + struct.pack("<I", len(raw)) + raw
        )
    return bytes(data) + b"\0"


def _keyfile(data):
    if not data or len(data) > MAX_KEYFILE:
        raise invalid()
    if len(data) == 32:
        return data
    if data.lstrip().startswith(b"<"):
        root = SafeXML.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        version = root.findtext("Meta/Version", "")
        element = root.find("Key/Data")
        if root.tag != "KeyFile" or element is None:
            raise invalid()
        value = "".join((element.text or "").split())
        if version.startswith("1."):
            key = base64.b64decode(value, validate=True)
        elif version.startswith("2."):
            key = bytes.fromhex(value)
            if not hmac.compare_digest(
                hashlib.sha256(key).hexdigest()[:8].upper(), element.get("Hash", "").upper()
            ):
                raise invalid()
        else:
            raise unsupported("Use a KeePass XML key file version 1 or 2, or a binary key file.")
        if len(key) != 32:
            raise invalid()
        return key
    if len(data) == 64:
        try:
            return bytes.fromhex(data.decode("ascii"))
        except (ValueError, UnicodeError):
            pass
    return hashlib.sha256(data).digest()


def _derive(parameters, password, keyfile):
    parts = []
    if password is not None:
        parts.append(hashlib.sha256(password.encode("utf-8")).digest())
    if keyfile is not None:
        parts.append(_keyfile(keyfile))
    if not parts:
        raise invalid()
    composite = hashlib.sha256(b"".join(parts)).digest()
    algorithm = parameters.get("$UUID")
    salt = parameters.get("S")
    if not isinstance(salt, bytes):
        raise invalid()
    if algorithm == AES_KDF:
        rounds = parameters.get("R")
        if len(salt) != 32 or type(rounds) is not int or not 1 <= rounds <= 1_000_000:
            raise unsupported(
                "AES-KDF imports support 1–1,000,000 rounds. Lower the transfer copy's KDF cost in KeePass."
            )
        if set(parameters) != {"$UUID", "S", "R"}:
            raise unsupported("Additional AES-KDF parameters are not supported.")
        cipher = AES.new(salt, AES.MODE_ECB)
        for _ in range(rounds):
            composite = cipher.encrypt(composite)
        return hashlib.sha256(composite).digest()
    if algorithm not in {ARGON_D, ARGON_ID}:
        raise unsupported("Use AES-KDF, Argon2d or Argon2id without a key-provider plugin.")
    if set(parameters) != {"$UUID", "S", "I", "M", "P", "V"}:
        raise unsupported("Additional Argon2 parameters are not supported.")
    memory, iterations, parallelism, version = (parameters.get(k) for k in ("M", "I", "P", "V"))
    if (
        any(type(v) is not int for v in (memory, iterations, parallelism, version))
        or not 8 <= len(salt) <= 64
        or version not in {0x10, 0x13}
        or not 1 <= parallelism <= 4
        or not 8192 * parallelism <= memory <= 64 * 1024**2
        or memory % 1024
        or not 1 <= iterations <= 32
    ):
        raise unsupported(
            "This transfer supports Argon2 up to 64 MiB, 32 iterations and 4 lanes. Lower the transfer copy's KDF cost in KeePass."
        )
    try:
        return hash_secret_raw(
            composite,
            salt,
            iterations,
            memory // 1024,
            parallelism,
            32,
            Type.D if algorithm == ARGON_D else Type.ID,
            version,
        )
    except HashingError:
        raise ServiceError(
            503,
            "keepass_resources",
            "The host could not allocate the KeePass key derivation resources. Try a transfer copy with a lower KDF cost.",
        ) from None


def _mac(key, index, data):
    block_key = hashlib.sha512(struct.pack("<Q", index) + key).digest()
    return hmac.new(block_key, data, hashlib.sha256).digest()


def _inflate(data):
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    result = inflater.decompress(data, MAX_PAYLOAD + 1)
    if (
        len(result) > MAX_PAYLOAD
        or not inflater.eof
        or inflater.unused_data
        or inflater.unconsumed_tail
    ):
        raise unsupported(
            "The decompressed KeePass file exceeds 2 MB or has an unsupported compressed stream."
        )
    return result


def _inner_cipher(kind, key):
    if kind == 2 and len(key) == 32:
        return Salsa20.new(
            key=hashlib.sha256(key).digest(), nonce=bytes.fromhex("e830094b97205d2a")
        )
    if kind == 3 and len(key) == 64:
        digest = hashlib.sha512(key).digest()
        return ChaCha20.new(key=digest[:32], nonce=digest[32:44])
    raise unsupported("Use Salsa20 or ChaCha20 protected fields in the KDBX 4 file.")


def _uuid(text):
    raw = base64.b64decode(text or "", validate=True)
    if len(raw) != 16:
        raise invalid()
    return str(UUID(bytes=raw))


def _extract(payload):
    reader, inner, attachments = Reader(payload), {}, 0
    while True:
        kind, value = reader.field()
        if kind == 0:
            if value:
                raise invalid()
            break
        if kind == 3:
            attachments += 1
            if not value:
                raise invalid()
        elif kind in {1, 2} and kind not in inner:
            inner[kind] = value
        else:
            raise unsupported("This KeePass inner header is not supported.")
    cipher = _inner_cipher(int.from_bytes(inner[1], "little"), inner[2])
    root = SafeXML.fromstring(
        reader.read(reader.remaining), forbid_dtd=True, forbid_entities=True, forbid_external=True
    )
    if root.tag != "KeePassFile":
        raise invalid()
    nodes = list(root.iter())
    if len(nodes) > 20_000:
        raise unsupported("This KeePass document has too many elements.")
    # Consume every protected field in document order, including omitted history.
    for node in nodes:
        if node.get("Protected", "").lower() == "true":
            node.text = cipher.decrypt(base64.b64decode(node.text or "", validate=True)).decode(
                "utf-8"
            )
    recycle = root.findtext("Meta/RecycleBinUUID")
    deleted = {item.findtext("UUID") for item in root.findall("Root/DeletedObjects/DeletedObject")}
    groups = root.findall("Root/Group")
    if len(groups) != 1:
        raise invalid()
    entries, seen = [], set()
    omitted = {
        "history_entries": len(root.findall(".//History/Entry")),
        "attachments": attachments,
        "recycled_entries": 0,
    }

    def walk(group, path, excluded=False):
        if len(path) > 24:
            raise unsupported("Use at most 24 nested KeePass groups.")
        raw_id, name = group.findtext("UUID"), group.findtext("Name", "")
        if len(name.encode("utf-8")) > 2048:
            raise unsupported("KeePass group names must fit within 2048 UTF-8 bytes.")
        group_id = _uuid(raw_id)
        excluded = excluded or raw_id == recycle or raw_id in deleted
        current_path = path + [{"id": group_id, "name": name}]
        for element in group.findall("Entry"):
            if excluded or element.findtext("UUID") in deleted:
                omitted["recycled_entries"] += 1
                continue
            identifier = _uuid(element.findtext("UUID"))
            if identifier in seen or len(entries) >= 100:
                raise unsupported(
                    "Choose at most 100 current KeePass entries with distinct identifiers."
                )
            seen.add(identifier)
            fields, keys = [], set()
            for kind, children in (
                ("string", element.findall("String")),
                ("custom-data", element.findall("CustomData/Item")),
            ):
                for child in children:
                    key, value = child.findtext("Key"), child.findtext("Value", "")
                    if (
                        not key
                        or len(key.encode("utf-8")) > 2048
                        or (kind, key) in keys
                        or len(value.encode("utf-8")) > 65536
                    ):
                        raise unsupported(
                            "KeePass fields must have distinct names and values of at most 65536 UTF-8 bytes."
                        )
                    keys.add((kind, key))
                    fields.append({"kind": kind, "name": key, "value": value})
            if len(fields) > 100 or not any(field["value"] for field in fields):
                raise unsupported(
                    "Choose entries with at most 100 fields and at least one nonempty current value."
                )
            title = next(
                (
                    field["value"]
                    for field in fields
                    if field["kind"] == "string" and field["name"] == "Title"
                ),
                "",
            )
            entries.append(
                {"id": identifier, "groups": current_path, "title": title, "fields": fields}
            )
        for child in group.findall("Group"):
            walk(child, current_path, excluded)

    walk(groups[0], [])
    if (
        not entries
        or sum(bool(field["value"]) for entry in entries for field in entry["fields"]) > MAX_FIELDS
    ):
        raise unsupported("Choose a transfer with 1–500 nonempty current credential fields.")
    return {"entries": entries, "omitted": omitted}


def load(data, password, keyfile=None):
    if not 64 <= len(data) <= MAX_FILE:
        raise unsupported("Choose a KDBX 4 file no larger than 1 MB.")
    try:
        reader, header = Reader(data), {}
        if reader.read(8) != SIGNATURE or reader.number(4) not in {0x00040000, 0x00040001}:
            raise unsupported("This import supports KDBX 4.0 and 4.1 files.")
        while True:
            kind, value = reader.field()
            if reader.pos > MAX_HEADER:
                raise unsupported("The KeePass header exceeds its transfer limit.")
            if kind == 0:
                if value != b"\r\n\r\n":
                    raise invalid()
                break
            if kind not in {2, 3, 4, 7, 11, 12} or kind in header:
                raise unsupported("This KeePass outer header is not supported.")
            header[kind] = value
        encoded_header = data[: reader.pos]
        if not hmac.compare_digest(reader.read(32), hashlib.sha256(encoded_header).digest()):
            raise invalid()
        if len(header[4]) != 32 or len(header[3]) != 4:
            raise invalid()
        algorithm = header[2]
        if algorithm not in {AES_ID, CHACHA_ID} or len(header[7]) != (
            16 if algorithm == AES_ID else 12
        ):
            raise unsupported("Use AES-256 or ChaCha20 KDBX encryption.")
        transformed = _derive(_dictionary(header[11]), password, keyfile)
        master = header[4] + transformed
        mac_key = hashlib.sha512(master + b"\x01").digest()
        if not hmac.compare_digest(reader.read(32), _mac(mac_key, 2**64 - 1, encoded_header)):
            raise invalid()
        encrypted, index = bytearray(), 0
        while True:
            expected, size = reader.read(32), reader.number(4)
            block = reader.read(size)
            actual = _mac(mac_key, index, struct.pack("<QI", index, size) + block)
            if not hmac.compare_digest(expected, actual):
                raise invalid()
            if not size:
                if reader.remaining:
                    raise invalid()
                break
            encrypted.extend(block)
            index += 1
        key = hashlib.sha256(master).digest()
        if algorithm == AES_ID:
            plaintext = unpad(
                AES.new(key, AES.MODE_CBC, iv=header[7]).decrypt(bytes(encrypted)), 16
            )
        else:
            plaintext = ChaCha20.new(key=key, nonce=header[7]).decrypt(bytes(encrypted))
        compression = int.from_bytes(header[3], "little")
        if compression == 1:
            plaintext = _inflate(plaintext)
        elif compression != 0:
            raise unsupported("Use uncompressed or GZip-compressed KDBX files.")
        if len(plaintext) > MAX_PAYLOAD:
            raise unsupported("The decrypted KeePass document exceeds 2 MB.")
        return _extract(plaintext)
    except ServiceError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        ET.ParseError,
        DefusedXmlException,
        zlib.error,
        RecursionError,
    ):
        raise invalid() from None


def _field(kind, value):
    return bytes([kind]) + struct.pack("<I", len(value)) + value


def _element(parent, tag, text):
    if any(
        not (
            char in "\t\n\r"
            or 0x20 <= ord(char) <= 0xD7FF
            or 0xE000 <= ord(char) <= 0xFFFD
            or 0x10000 <= ord(char) <= 0x10FFFF
        )
        for char in text
    ):
        raise unsupported(
            "A group, field name or custom-data value contains characters that KDBX XML cannot represent."
        )
    node = ET.SubElement(parent, tag)
    node.text = text
    return node


def _times(parent):
    timestamp = int(
        (datetime.now(timezone.utc) - datetime(1, 1, 1, tzinfo=timezone.utc)).total_seconds()
    )
    encoded = base64.b64encode(struct.pack("<Q", timestamp)).decode()
    times = ET.SubElement(parent, "Times")
    for name in (
        "CreationTime",
        "LastModificationTime",
        "LastAccessTime",
        "ExpiryTime",
        "LocationChanged",
    ):
        _element(times, name, encoded)
    _element(times, "Expires", "False")
    _element(times, "UsageCount", "0")


def dump(entries, password):
    """Export current fields as standard KDBX 4.1, AES-256/Argon2id/ChaCha20."""
    if not 1 <= len(entries) <= 100 or any(len(entry["fields"]) > 100 for entry in entries):
        raise unsupported("Choose at most 100 KeePass entries with at most 100 fields each.")
    inner_key = secrets.token_bytes(64)
    stream = _inner_cipher(3, inner_key)
    root = ET.Element("KeePassFile")
    meta = ET.SubElement(root, "Meta")
    _element(meta, "Generator", "Mnemion")
    _element(meta, "DatabaseName", "Mnemion credentials")
    _element(meta, "RecycleBinEnabled", "False")
    _element(meta, "RecycleBinUUID", base64.b64encode(bytes(16)).decode())
    protection = ET.SubElement(meta, "MemoryProtection")
    for name in ("Title", "UserName", "Password", "URL", "Notes"):
        _element(protection, "Protect" + name, "True")
    xml_root = ET.SubElement(root, "Root")
    parent = ET.SubElement(xml_root, "Group")
    first_groups = entries[0].get("groups", []) if entries else []
    common_root = (
        first_groups[0]
        if first_groups
        and all(entry.get("groups", [])[:1] == first_groups[:1] for entry in entries)
        else None
    )
    if any(len(entry.get("groups", [])) > (25 if common_root else 24) for entry in entries):
        raise unsupported(
            "Export deeply nested KeePass groups separately so the file stays within the supported group limit."
        )
    root_id = UUID(common_root["id"]) if common_root else uuid4()
    _element(parent, "UUID", base64.b64encode(root_id.bytes).decode())
    _element(parent, "Name", common_root["name"] if common_root else "Mnemion export")
    _times(parent)
    groups, used_ids = {}, set()
    for entry in entries:
        destination, path = parent, ()
        for group in entry.get("groups", [])[1:] if common_root else entry.get("groups", []):
            path += ((group["id"], group["name"]),)
            if path not in groups:
                node = ET.SubElement(destination, "Group")
                _element(node, "UUID", base64.b64encode(uuid4().bytes).decode())
                _element(node, "Name", group["name"])
                _times(node)
                groups[path] = node
            destination = groups[path]
        node = ET.SubElement(destination, "Entry")
        identifier = UUID(entry["id"])
        if identifier in used_ids:
            identifier = uuid4()
        used_ids.add(identifier)
        _element(node, "UUID", base64.b64encode(identifier.bytes).decode())
        _times(node)
        custom = None
        for field in entry["fields"]:
            if field["kind"] == "custom-data":
                if custom is None:
                    custom = ET.SubElement(node, "CustomData")
                item = ET.SubElement(custom, "Item")
                _element(item, "Key", field["name"])
                _element(item, "Value", field["value"])
            else:
                item = ET.SubElement(node, "String")
                _element(item, "Key", field["name"])
                value = _element(
                    item,
                    "Value",
                    base64.b64encode(stream.encrypt(field["value"].encode("utf-8"))).decode(),
                )
                value.set("Protected", "True")
        ET.SubElement(node, "History")
    ET.SubElement(xml_root, "DeletedObjects")
    if sum(1 for _ in root.iter()) > 20_000:
        raise unsupported(
            "Choose fewer credentials; their empty fields and grouping exceed the XML element limit."
        )
    payload = (
        _field(1, struct.pack("<I", 3))
        + _field(2, inner_key)
        + _field(0, b"")
        + ET.tostring(root, encoding="utf-8", xml_declaration=True).replace(b"\r", b"&#13;")
    )
    if len(payload) > MAX_PAYLOAD:
        raise unsupported("Choose fewer credentials; the KeePass export exceeds 2 MB.")
    parameters = {
        "$UUID": (0x42, ARGON_ID),
        "V": (4, 0x13),
        "I": (5, 3),
        "M": (5, 32 * 1024**2),
        "P": (4, 1),
        "S": (0x42, secrets.token_bytes(32)),
    }
    seed, iv = secrets.token_bytes(32), secrets.token_bytes(16)
    header = SIGNATURE + struct.pack("<I", 0x00040001)
    for kind, value in (
        (2, AES_ID),
        (3, struct.pack("<I", 0)),
        (4, seed),
        (7, iv),
        (11, _encode_dictionary(parameters)),
        (0, b"\r\n\r\n"),
    ):
        header += _field(kind, value)
    transformed = _derive({key: value for key, (_, value) in parameters.items()}, password, None)
    key = hashlib.sha256(seed + transformed).digest()
    mac_key = hashlib.sha512(seed + transformed + b"\x01").digest()
    encrypted = AES.new(key, AES.MODE_CBC, iv=iv).encrypt(pad(payload, 16))
    output = header + hashlib.sha256(header).digest() + _mac(mac_key, 2**64 - 1, header)
    for index, block in enumerate((encrypted, b"")):
        size = struct.pack("<I", len(block))
        output += _mac(mac_key, index, struct.pack("<Q", index) + size + block) + size + block
    if len(output) > MAX_FILE:
        raise unsupported("Choose fewer credentials; the KeePass export exceeds 1 MB.")
    return output
