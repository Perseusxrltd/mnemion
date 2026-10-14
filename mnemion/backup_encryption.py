"""Portable authenticated backup files with bounded streaming memory.

Recovery keys are randomly generated 256-bit values, never human passwords.
The header is authenticated; unauthenticated plaintext is never published.
This module does not save keys, execute archives or configure cloud storage.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import struct
from typing import Callable, Literal
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .archives import MAX_ARCHIVE_BYTES, canonical_json, publish_file
from .private_output import private_output

MAGIC = b"MNMENC1\n"
HEADER_LIMIT = 1024
CHUNK_BYTES = 1024 * 1024
TAG_BYTES = 16
KEY_PREFIX = "mnm_bk_"
Kind = Literal["snapshot", "ledger", "bundle"]
KINDS = {"snapshot", "ledger", "bundle"}


class EncryptionError(ValueError):
    """A public-safe error that never contains input, key or plaintext bytes."""


class EncryptionCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class Receipt:
    kind: Kind
    key_id: str
    plaintext_bytes: int
    encrypted_bytes: int
    plaintext_sha256: str
    encrypted_sha256: str
    authenticated: bool


def new_key() -> str:
    """Return a secret for an explicit recovery-key export, not ordinary status."""
    return KEY_PREFIX + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def _key(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"mnm_bk_[A-Za-z0-9_-]{43}", value):
        raise EncryptionError("Use the complete exported Mnemion recovery key.")
    decoded = base64.urlsafe_b64decode(value[len(KEY_PREFIX) :] + "=")
    if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != value[len(KEY_PREFIX) :]:
        raise EncryptionError("Use the complete exported Mnemion recovery key.")
    return decoded


def key_id(value: str) -> str:
    return hashlib.sha256(b"mnemion-backup-key-v1\0" + _key(value)).hexdigest()[:24]


def _cancel(check: Callable[[], bool] | None) -> None:
    if check is not None and check():
        raise EncryptionCancelled("The backup operation was cancelled.")


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _remove_owned(path: Path, identity) -> None:
    if identity is None:
        return
    try:
        current = path.lstat()
        if (current.st_dev, current.st_ino) == identity:
            path.unlink()
    except FileNotFoundError:
        pass


@contextmanager
def _ciphertext_output(path: Path):
    # This destination may be shared or on exFAT. Only ciphertext and its
    # authenticated format header enter it; private plaintext staging uses the
    # stricter private_output helper. Do not change a user's folder permissions.
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    original = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as writer:
            yield writer
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        _remove_owned(path, (original.st_dev, original.st_ino))
        raise


@contextmanager
def _source(path: Path, maximum: int):
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or getattr(before, "st_file_attributes", 0) & 0x400:
        raise EncryptionError("Choose an ordinary downloaded backup file, not a link or device.")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if _identity(opened) != _identity(before) or not 0 <= opened.st_size <= maximum:
            raise EncryptionError("The backup input changed or exceeds the supported size.")
        yield stream, opened.st_size
        if _identity(os.fstat(stream.fileno())) != _identity(opened):
            raise EncryptionError("The backup input changed while it was being read.")


def _exact(stream, length: int) -> bytes:
    value = stream.read(length)
    if len(value) != length:
        raise EncryptionError("The encrypted backup is incomplete or damaged.")
    return value


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate header field")
        result[name] = value
    return result


def _header(stream, size: int, secret: str):
    prefix = _exact(stream, len(MAGIC) + 4)
    if prefix[: len(MAGIC)] != MAGIC:
        raise EncryptionError("This is not a supported encrypted Mnemion backup.")
    length = struct.unpack(">I", prefix[len(MAGIC) :])[0]
    if not 1 <= length <= HEADER_LIMIT:
        raise EncryptionError("The encrypted backup header is invalid.")
    encoded = _exact(stream, length)
    try:
        header = json.loads(encoded, object_pairs_hook=_unique)
        if (
            not isinstance(header, dict)
            or set(header) != {"algorithm", "kind", "key_id", "nonce", "plaintext_bytes"}
            or header["algorithm"] != "AES-256-GCM"
            or not isinstance(header["kind"], str)
            or header["kind"] not in KINDS
            or type(header["plaintext_bytes"]) is not int
            or not 0 <= header["plaintext_bytes"] <= MAX_ARCHIVE_BYTES
            or not isinstance(header["key_id"], str)
            or not re.fullmatch(r"[a-f0-9]{24}", header["key_id"])
            or not isinstance(header["nonce"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{16}", header["nonce"])
        ):
            raise ValueError("Invalid header")
        nonce = base64.urlsafe_b64decode(header["nonce"])
    except (ValueError, TypeError, RecursionError):
        raise EncryptionError("The encrypted backup header is invalid.") from None
    if size != len(prefix) + length + header["plaintext_bytes"] + TAG_BYTES:
        raise EncryptionError("The encrypted backup is incomplete or has unexpected extra bytes.")
    if not hmac.compare_digest(header["key_id"], key_id(secret)):
        raise EncryptionError("This recovery key does not unlock the selected backup.")
    return header, nonce, prefix + encoded


def encrypt_file(
    source: Path,
    output: Path,
    secret: str,
    *,
    kind: Kind,
    cancelled: Callable[[], bool] | None = None,
) -> Receipt:
    """Publish ciphertext exclusively; a later verify_file confirms read-back."""
    key = _key(secret)
    if not isinstance(kind, str) or kind not in KINDS:
        raise EncryptionError("Choose a supported backup payload type.")
    output = Path(output)
    staged = output.parent / (".mnemion-encrypted-" + uuid4().hex + ".part")
    plain_digest, encrypted_digest = hashlib.sha256(), hashlib.sha256()
    staged_identity = None
    try:
        with _source(source, MAX_ARCHIVE_BYTES) as (reader, size):
            _cancel(cancelled)
            nonce = secrets.token_bytes(12)
            header = {
                "algorithm": "AES-256-GCM",
                "kind": kind,
                "key_id": key_id(secret),
                "nonce": base64.urlsafe_b64encode(nonce).decode(),
                "plaintext_bytes": size,
            }
            encoded = canonical_json(header)
            prefix = MAGIC + struct.pack(">I", len(encoded)) + encoded
            encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
            encryptor.authenticate_additional_data(prefix)
            with _ciphertext_output(staged) as writer:
                info = os.fstat(writer.fileno())
                staged_identity = info.st_dev, info.st_ino
                writer.write(prefix)
                encrypted_digest.update(prefix)
                remaining = size
                while remaining:
                    _cancel(cancelled)
                    block = _exact(reader, min(CHUNK_BYTES, remaining))
                    plain_digest.update(block)
                    encrypted = encryptor.update(block)
                    writer.write(encrypted)
                    encrypted_digest.update(encrypted)
                    remaining -= len(block)
                final = encryptor.finalize() + encryptor.tag
                writer.write(final)
                encrypted_digest.update(final)
        _cancel(cancelled)
        publish_file(staged, output)
        return Receipt(
            kind,
            header["key_id"],
            size,
            len(prefix) + size + TAG_BYTES,
            plain_digest.hexdigest(),
            encrypted_digest.hexdigest(),
            False,
        )
    finally:
        _remove_owned(staged, staged_identity)


def _decrypt(
    source: Path,
    secret: str,
    writer=None,
    *,
    expected_kind: Kind | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Receipt:
    key = _key(secret)
    plain_digest, encrypted_digest = hashlib.sha256(), hashlib.sha256()
    with _source(source, MAX_ARCHIVE_BYTES + HEADER_LIMIT + len(MAGIC) + 4 + TAG_BYTES) as (
        reader,
        size,
    ):
        _cancel(cancelled)
        header, nonce, prefix = _header(reader, size, secret)
        if expected_kind is not None and header["kind"] != expected_kind:
            raise EncryptionError("Choose the expected snapshot, ledger or recovery bundle.")
        encrypted_digest.update(prefix)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).decryptor()
        decryptor.authenticate_additional_data(prefix)
        remaining = header["plaintext_bytes"]
        while remaining:
            _cancel(cancelled)
            block = _exact(reader, min(CHUNK_BYTES, remaining))
            encrypted_digest.update(block)
            plaintext = decryptor.update(block)
            plain_digest.update(plaintext)
            if writer is not None:
                writer.write(plaintext)
            remaining -= len(block)
        tag = _exact(reader, TAG_BYTES)
        encrypted_digest.update(tag)
        try:
            final = decryptor.finalize_with_tag(tag)
        except InvalidTag:
            raise EncryptionError(
                "The recovery key is wrong or this backup has been changed."
            ) from None
        plain_digest.update(final)
        if writer is not None:
            writer.write(final)
        _cancel(cancelled)
    return Receipt(
        header["kind"],
        header["key_id"],
        header["plaintext_bytes"],
        size,
        plain_digest.hexdigest(),
        encrypted_digest.hexdigest(),
        True,
    )


def verify_file(
    source: Path,
    secret: str,
    *,
    expected_kind: Kind | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Receipt:
    """Authenticate all bytes without retaining any plaintext output."""
    return _decrypt(source, secret, expected_kind=expected_kind, cancelled=cancelled)


def decrypt_file(
    source: Path,
    output: Path,
    secret: str,
    *,
    expected_kind: Kind | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Receipt:
    """Publish an authenticated private file; callers own its eventual cleanup."""
    output = Path(output)
    staged = output.parent / (".mnemion-decrypted-" + uuid4().hex + ".part")
    staged_identity = None
    try:
        with private_output(staged) as writer:
            info = os.fstat(writer.fileno())
            staged_identity = info.st_dev, info.st_ino
            receipt = _decrypt(
                source, secret, writer, expected_kind=expected_kind, cancelled=cancelled
            )
        _cancel(cancelled)
        publish_file(staged, output)
        return receipt
    finally:
        _remove_owned(staged, staged_identity)
