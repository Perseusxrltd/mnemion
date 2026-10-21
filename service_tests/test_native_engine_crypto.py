"""Exercise native entry initialization in a fresh interpreter, before crypto loads."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_native_engine_uses_required_crypto_without_the_optional_legacy_provider():
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ}
    environment.pop("CRYPTOGRAPHY_OPENSSL_NO_LEGACY", None)
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                import contextlib, io, runpy, sys
                entry = sys.argv[1]
                sys.argv = [entry, '--help']
                with contextlib.redirect_stdout(io.StringIO()):
                    try:
                        runpy.run_path(entry, run_name='__main__')
                    except SystemExit as outcome:
                        assert outcome.code == 0

                from cryptography.exceptions import InvalidTag, InvalidSignature
                from cryptography.hazmat.backends.openssl.backend import backend
                from cryptography.hazmat.decrepit.ciphers.algorithms import Blowfish
                from cryptography.hazmat.primitives.ciphers.modes import ECB
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                from cryptography.hazmat.primitives.asymmetric import rsa, padding
                from cryptography.hazmat.primitives import hashes
                from mnemion.service.passwords import hash_password, verify_password

                assert not backend.cipher_supported(Blowfish(b'fixture-only'), ECB())
                cipher = AESGCM(AESGCM.generate_key(bit_length=256))
                nonce, text, aad = b'N' * 12, b'Private fixture memory', b'fixture-v1'
                sealed = cipher.encrypt(nonce, text, aad)
                assert cipher.decrypt(nonce, sealed, aad) == text
                try:
                    cipher.decrypt(nonce, sealed, b'wrong-binding')
                except InvalidTag:
                    pass
                else:
                    raise AssertionError('Changed capture binding was accepted')
                key = Ed25519PrivateKey.generate()
                signature = key.sign(text)
                key.public_key().verify(signature, text)
                try:
                    key.public_key().verify(signature, text + b'changed')
                except InvalidSignature:
                    pass
                else:
                    raise AssertionError('Changed signed update was accepted')
                rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                rsa_signature = rsa_key.sign(text, padding.PKCS1v15(), hashes.SHA256())
                rsa_key.public_key().verify(rsa_signature, text, padding.PKCS1v15(), hashes.SHA256())
                verifier = hash_password('Disposable fixture password')
                assert verify_password('Disposable fixture password', verifier)
                assert not verify_password('Different fixture password', verifier)
                print('Native AES-GCM, Ed25519, RSA and Argon2id passed without legacy crypto')
                """
            ),
            str(root / "studio/engine/main.py"),
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert child.returncode == 0, child.stderr
    assert child.stderr == ""
    assert "passed without legacy crypto" in child.stdout
