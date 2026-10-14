"""Portable encryption, authenticated publication and bounded recovery work."""

from contextlib import contextmanager
from dataclasses import asdict
import base64
import hashlib
import json
import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pytest

from mnemion import backup_encryption as encryption


def fixture(tmp_path, *, kind="snapshot", content=b"Private synthetic memory and access ledger."):
    original, encrypted = tmp_path / "source", tmp_path / "backup.mnemion.enc"
    original.write_bytes(content)
    key = encryption.new_key()
    receipt = encryption.encrypt_file(original, encrypted, key, kind=kind)
    return original, encrypted, key, receipt


@pytest.mark.parametrize("size", [0, 217, encryption.CHUNK_BYTES * 3 + 73])
def test_complete_roundtrip_verifies_every_byte_and_keeps_only_public_receipts(tmp_path, size):
    payload = (b"Private synthetic memory and permission evidence. " * (size // 49 + 1))[:size]
    original, encrypted, key, written = fixture(tmp_path, content=payload)
    checked = encryption.verify_file(encrypted, key, expected_kind="snapshot")
    output = tmp_path / "recovered"
    recovered = encryption.decrypt_file(encrypted, output, key, expected_kind="snapshot")
    assert output.read_bytes() == original.read_bytes() == payload
    assert checked == recovered
    assert checked.authenticated and not written.authenticated
    assert checked.plaintext_bytes == len(payload)
    assert checked.encrypted_bytes == encrypted.stat().st_size
    assert checked.plaintext_sha256 == hashlib.sha256(payload).hexdigest()
    assert checked.encrypted_sha256 == hashlib.sha256(encrypted.read_bytes()).hexdigest()
    assert asdict(checked) == {**asdict(written), "authenticated": True}
    assert key not in json.dumps(asdict(checked))
    if payload:
        assert payload[:32] not in encrypted.read_bytes()
    if os.name != "nt":
        assert encrypted.stat().st_mode & 0o777 == 0o600
        assert output.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".mnemion-*.part"))


def test_streaming_cipher_matches_one_shot_aead_api(tmp_path):
    original, encrypted, key, _ = fixture(tmp_path)
    raw = encrypted.read_bytes()
    length = struct.unpack(">I", raw[len(encryption.MAGIC) : len(encryption.MAGIC) + 4])[0]
    end = len(encryption.MAGIC) + 4 + length
    header = json.loads(raw[len(encryption.MAGIC) + 4 : end])
    nonce = base64.urlsafe_b64decode(header["nonce"])
    secret = base64.urlsafe_b64decode(key[len(encryption.KEY_PREFIX) :] + "=")
    assert raw[end:] == AESGCM(secret).encrypt(nonce, original.read_bytes(), raw[:end])


@pytest.mark.parametrize("change", ["header", "body", "tag", "truncated", "appended", "key"])
def test_changed_or_truncated_backup_never_publishes_plaintext(tmp_path, change):
    _, encrypted, key, _ = fixture(tmp_path, kind="ledger")
    raw = bytearray(encrypted.read_bytes())
    if change == "header":
        start = raw.index(b'"ledger"')
        raw[start : start + 8] = (
            b'"bundle"'  # Still a valid header; its GCM authentication changes.
        )
    elif change == "body":
        raw[-encryption.TAG_BYTES - 1] ^= 1
    elif change == "tag":
        raw[-1] ^= 1
    elif change == "truncated":
        del raw[-1]
    elif change == "appended":
        raw += b"trailing bytes"
    else:
        key = encryption.new_key()
    encrypted.write_bytes(raw)
    output = tmp_path / "recovered"
    with pytest.raises(encryption.EncryptionError) as error:
        encryption.decrypt_file(encrypted, output, key)
    assert key not in str(error.value)
    assert not output.exists()
    assert not list(tmp_path.glob(".mnemion-*.part"))


def test_key_identifier_is_not_authority_to_decrypt_a_different_key(tmp_path):
    _, encrypted, key, _ = fixture(tmp_path)
    other = encryption.new_key()
    raw = encrypted.read_bytes().replace(
        encryption.key_id(key).encode(), encryption.key_id(other).encode()
    )
    encrypted.write_bytes(raw)
    with pytest.raises(encryption.EncryptionError, match="changed"):
        encryption.verify_file(encrypted, other)


def test_wrong_payload_type_cannot_be_used_as_a_recovery_ledger(tmp_path):
    _, encrypted, key, _ = fixture(tmp_path)
    with pytest.raises(encryption.EncryptionError, match="expected"):
        encryption.verify_file(encrypted, key, expected_kind="ledger")


@pytest.mark.parametrize("operation", ["encrypt", "decrypt"])
def test_existing_outputs_are_never_replaced(tmp_path, operation):
    original, encrypted, key, _ = fixture(tmp_path)
    output = tmp_path / "existing"
    output.write_bytes(b"Existing recovery material")
    with pytest.raises(FileExistsError):
        if operation == "encrypt":
            encryption.encrypt_file(original, output, key, kind="snapshot")
        else:
            encryption.decrypt_file(encrypted, output, key)
    assert output.read_bytes() == b"Existing recovery material"
    assert not list(tmp_path.glob(".mnemion-*.part"))


@pytest.mark.parametrize("operation", ["encrypt", "decrypt", "verify"])
def test_cancellation_cleans_partial_output_and_keeps_original_material(tmp_path, operation):
    original, encrypted, key, _ = fixture(tmp_path, content=b"s" * (encryption.CHUNK_BYTES + 1))
    original_bytes, encrypted_bytes = original.read_bytes(), encrypted.read_bytes()
    attempts = 0

    def cancelled():
        nonlocal attempts
        attempts += 1
        return attempts >= 3

    output = tmp_path / "cancelled"
    with pytest.raises(encryption.EncryptionCancelled):
        if operation == "encrypt":
            encryption.encrypt_file(original, output, key, kind="snapshot", cancelled=cancelled)
        elif operation == "decrypt":
            encryption.decrypt_file(encrypted, output, key, cancelled=cancelled)
        else:
            encryption.verify_file(encrypted, key, cancelled=cancelled)
    assert not output.exists()
    assert original.read_bytes() == original_bytes and encrypted.read_bytes() == encrypted_bytes
    assert not list(tmp_path.glob(".mnemion-*.part"))


def test_changes_during_encryption_are_not_reported_as_a_consistent_backup(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"original")
    output = tmp_path / "backup"
    calls = 0

    def changed():
        nonlocal calls
        calls += 1
        if calls == 2:
            source.write_bytes(b"modified source")
        return False

    with pytest.raises(encryption.EncryptionError, match="changed"):
        encryption.encrypt_file(
            source, output, encryption.new_key(), kind="snapshot", cancelled=changed
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".mnemion-*.part"))


def test_read_requests_remain_bounded_for_large_payloads(tmp_path, monkeypatch):
    original, encrypted, key, _ = fixture(tmp_path, content=b"m" * (encryption.CHUNK_BYTES * 4 + 7))
    source = encryption._source
    reads = []

    @contextmanager
    def bounded(path, maximum):
        with source(path, maximum) as (stream, size):

            class Reader:
                def read(self, count):
                    assert 0 <= count <= encryption.CHUNK_BYTES
                    reads.append(count)
                    return stream.read(count)

            yield Reader(), size

    monkeypatch.setattr(encryption, "_source", bounded)
    encryption.encrypt_file(original, tmp_path / "another", key, kind="snapshot")
    encryption.verify_file(encrypted, key)
    assert reads.count(encryption.CHUNK_BYTES) >= 8


def test_rejects_oversized_and_duplicate_headers_before_allocating_or_writing(tmp_path):
    _, encrypted, key, _ = fixture(tmp_path)
    raw = encrypted.read_bytes()
    offset = len(encryption.MAGIC)
    output = tmp_path / "recovered"
    oversized = encryption.MAGIC + struct.pack(">I", encryption.HEADER_LIMIT + 1)
    encrypted.write_bytes(oversized)
    with pytest.raises(encryption.EncryptionError, match="header"):
        encryption.decrypt_file(encrypted, output, key)
    length = struct.unpack(">I", raw[offset : offset + 4])[0]
    header = raw[offset + 4 : offset + 4 + length]
    duplicate = header[:-1] + b',"plaintext_bytes":0}'
    encrypted.write_bytes(
        encryption.MAGIC
        + struct.pack(">I", len(duplicate))
        + duplicate
        + raw[offset + 4 + length :]
    )
    with pytest.raises(encryption.EncryptionError, match="header"):
        encryption.decrypt_file(encrypted, output, key)
    assert not output.exists()


def test_input_limit_and_link_checks_happen_before_streaming(tmp_path, monkeypatch):
    original, _, key, _ = fixture(tmp_path)
    monkeypatch.setattr(encryption, "MAX_ARCHIVE_BYTES", 4)
    with pytest.raises(encryption.EncryptionError, match="size"):
        encryption.encrypt_file(original, tmp_path / "too-big", key, kind="snapshot")
    if os.name != "nt":
        link = tmp_path / "linked"
        link.symlink_to(original)
        with pytest.raises(encryption.EncryptionError, match="link"):
            encryption.encrypt_file(link, tmp_path / "invalid", key, kind="snapshot")
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        with pytest.raises(encryption.EncryptionError, match="device"):
            encryption.verify_file(fifo, key)


def test_human_passwords_and_noncanonical_key_encodings_are_refused(tmp_path):
    original = tmp_path / "source"
    original.write_bytes(b"memory")
    for secret in ("a human password is not a recovery key", "mnm_bk_" + "A" * 42 + "B"):
        with pytest.raises(encryption.EncryptionError, match="complete exported") as error:
            encryption.encrypt_file(original, tmp_path / "invalid", secret, kind="snapshot")
        assert secret not in str(error.value)


@pytest.mark.parametrize("operation", ["encrypt", "decrypt"])
def test_staging_name_collision_never_removes_an_existing_file(tmp_path, monkeypatch, operation):
    from types import SimpleNamespace

    original, encrypted, key, _ = fixture(tmp_path)
    identifier = "a" * 32
    monkeypatch.setattr(encryption, "uuid4", lambda: SimpleNamespace(hex=identifier))
    ending = "encrypted" if operation == "encrypt" else "decrypted"
    staged = tmp_path / (".mnemion-" + ending + "-" + identifier + ".part")
    staged.write_bytes(b"Unrelated existing file")
    with pytest.raises(FileExistsError):
        if operation == "encrypt":
            encryption.encrypt_file(original, tmp_path / "output", key, kind="snapshot")
        else:
            encryption.decrypt_file(encrypted, tmp_path / "output", key)
    assert staged.read_bytes() == b"Unrelated existing file"
