"""Password policy preserves exact input and bounds attacker-influenced work."""

import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.exceptions import InvalidKey

from mnemion.service import passwords
from mnemion.service.errors import ServiceError


def test_real_argon2_salts_and_exact_unicode_passphrases():
    phrase = "  Café passwords stay exact 🌐  "
    first, second = passwords.hash_password(phrase), passwords.hash_password(phrase)
    assert first != second and first.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert passwords.verify_password(phrase, first)
    assert passwords.verify_password(phrase, second)
    for changed in (phrase.strip(), phrase.upper(), unicodedata.normalize("NFD", phrase)):
        assert not passwords.verify_password(changed, first)
    assert not passwords.verify_password(phrase, None)
    assert not passwords.verify_password(phrase, "not-a-password-verifier")


@pytest.mark.parametrize("phrase", ["x" * 15, "🌐" * 128])
def test_password_boundaries_do_not_truncate(phrase):
    encoded = passwords.hash_password(phrase)
    assert passwords.verify_password(phrase, encoded)
    assert not passwords.verify_password(phrase + "x", encoded)


@pytest.mark.parametrize(
    "phrase", [None, b"not-a-string", "", "short", " " * 15, "x" * 129, "x" * 15 + "\ud800"]
)
def test_creation_rejects_invalid_input_without_echoing_it(phrase):
    with pytest.raises(ServiceError) as error:
        passwords.hash_password(phrase)
    assert error.value.status == 422 and error.value.code == "invalid_password"
    assert (
        error.value.message
        == "Choose a password of 15–128 characters, including at least one non-space character."
    )


@pytest.mark.parametrize(
    "encoded",
    [
        None,
        "",
        "$argon2id$v=19$m=2147483647,t=2,p=1$" + "A" * 22 + "$" + "A" * 43,
        "$argon2id$v=19$m=19456,t=2147483647,p=1$" + "A" * 22 + "$" + "A" * 43,
        "$argon2id$v=19$m=19456,t=2,p=255$" + "A" * 22 + "$" + "A" * 43,
        "$argon2i$v=19$m=19456,t=2,p=1$" + "A" * 22 + "$" + "A" * 43,
        "$argon2id$v=19$m=19456,t=2,p=1$" + "B" * 22 + "$" + "A" * 43,
        "A" * 100000,
    ],
)
def test_unapproved_parameters_never_reach_the_library_or_authenticate(monkeypatch, encoded):
    seen = []

    class Verifier:
        @staticmethod
        def verify_phc_encoded(value, phc):
            seen.append(phc)
            # Even hypothetical success of the dummy verifier cannot sign in.

    monkeypatch.setattr(passwords, "Argon2id", Verifier)
    assert not passwords.verify_password("a rejected password", encoded)
    assert seen == [passwords._DUMMY]


def test_hash_admission_is_shared_and_recovers_after_failures(monkeypatch):
    started = threading.Barrier(3)
    release = threading.Event()

    class Verifier:
        @staticmethod
        def verify_phc_encoded(value, phc):
            started.wait(timeout=5)
            if not release.wait(timeout=5):
                raise RuntimeError("Test did not release the occupied password slots")
            raise InvalidKey

    monkeypatch.setattr(passwords, "Argon2id", Verifier)
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = [
            executor.submit(passwords.verify_password, "bounded attempt", None) for _ in range(2)
        ]
        try:
            started.wait(timeout=5)
            for operation in (
                lambda: passwords.verify_password("another attempt", None),
                lambda: passwords.hash_password("another new password"),
            ):
                with pytest.raises(ServiceError) as busy:
                    operation()
                assert busy.value.status == 503 and busy.value.code == "sign_in_busy"
        finally:
            release.set()
        assert [future.result(timeout=5) for future in pending] == [False, False]
    monkeypatch.undo()
    # Failed verifications must not strand either process-wide admission slot.
    encoded = passwords.hash_password("subsequent valid password")
    assert passwords.verify_password("subsequent valid password", encoded)
