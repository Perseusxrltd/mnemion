"""Native encryption metadata checks, independent of model/service dependencies."""

import os

import pytest

from mnemion import backup_encryption as encryption


def test_native_metadata_allows_encryption_verification_and_decryption(tmp_path):
    source = tmp_path / "Private snapshot Équipe.bin"
    sealed = tmp_path / "Encrypted snapshot Équipe.mnemion.enc"
    restored = tmp_path / "Recovered snapshot Équipe.bin"
    source.write_bytes(b"Disposable private memory\n" * 100000)
    # Distinct creation/modification metadata exposes the Windows stat/fstat
    # discrepancy without relying on filesystem-clock scheduling precision.
    details = source.stat()
    os.utime(source, ns=(details.st_atime_ns, details.st_mtime_ns - 1_000_000_000))
    key = encryption.new_key()
    encryption.encrypt_file(source, sealed, key, kind="snapshot")
    verified = encryption.verify_file(sealed, key, expected_kind="snapshot")
    recovered = encryption.decrypt_file(sealed, restored, key, expected_kind="snapshot")
    assert verified.authenticated and recovered == verified
    assert restored.read_bytes() == source.read_bytes()


def test_modification_during_an_open_read_is_still_refused(tmp_path):
    path = tmp_path / "Changing snapshot.bin"
    path.write_bytes(b"before")
    with pytest.raises(encryption.EncryptionError, match="changed while"):
        with encryption._source(path, 1024) as (stream, size):
            assert size == 6 and stream.read() == b"before"
            path.write_bytes(b"changed during read")
