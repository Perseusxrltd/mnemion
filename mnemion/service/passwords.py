"""Bounded password hashing for the upcoming individual-account boundary.

Uses the existing cryptography runtime's Argon2id/PHC implementation. This
module does not enable sign-in or persist passwords. Account lookup, attempt
throttling, session issuance and recovery remain separate responsibilities.
"""

from __future__ import annotations

import base64
import re
import secrets
import threading
from contextlib import contextmanager

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from .errors import ServiceError

# OWASP's Argon2id minimum profile: 19 MiB, two iterations and one lane.
# Admission limits aggregate hashing work to two operations per API process.
MEMORY_KIB = 19 * 1024
ITERATIONS = 2
LANES = 1
MIN_CHARACTERS = 15
MAX_CHARACTERS = 128
MAX_UTF8_BYTES = 512
_CAPACITY = threading.BoundedSemaphore(2)
_PREFIX = f"$argon2id$v=19$m={MEMORY_KIB},t={ITERATIONS},p={LANES}$"
_PHC = re.compile(re.escape(_PREFIX) + r"([A-Za-z0-9+/]{22})\$([A-Za-z0-9+/]{43})\Z")
# Fixed dummy salt/digest, never a stored account or an accepted credential.
# Missing or malformed records still perform a full, bounded rejected check.
_DUMMY = _PREFIX + "A" * 22 + "$" + "A" * 43


@contextmanager
def _hashing_slot():
    if not _CAPACITY.acquire(blocking=False):
        raise ServiceError(503, "sign_in_busy", "Sign-in capacity is busy; retry shortly.")
    try:
        yield
    finally:
        _CAPACITY.release()


def _password_bytes(password: str, *, creating: bool) -> bytes:
    valid = isinstance(password, str) and 1 <= len(password) <= MAX_CHARACTERS
    if creating:
        valid = valid and len(password) >= MIN_CHARACTERS and bool(password.strip())
    if valid:
        try:
            value = password.encode("utf-8")
        except UnicodeEncodeError:
            valid = False
        else:
            if len(value) <= MAX_UTF8_BYTES:
                return value
    raise ServiceError(
        422,
        "invalid_password",
        "Choose a password of 15–128 characters, including at least one non-space character.",
    )


def _approved_hash(encoded: str | None) -> bool:
    # Never let malformed or attacker-influenced PHC parameters choose the
    # memory, work factor or lane count passed to the cryptography library.
    match = _PHC.fullmatch(encoded) if isinstance(encoded, str) and len(encoded) < 200 else None
    if match is None:
        return False
    for value, size in zip(match.groups(), (16, 32), strict=True):
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), validate=True)
        if len(decoded) != size or base64.b64encode(decoded).decode().rstrip("=") != value:
            return False
    return True


def hash_password(password: str) -> str:
    """Create a salted PHC verifier; no normalization, truncation or logging."""
    value = _password_bytes(password, creating=True)
    with _hashing_slot():
        return Argon2id(
            salt=secrets.token_bytes(16),
            length=32,
            iterations=ITERATIONS,
            lanes=LANES,
            memory_cost=MEMORY_KIB,
        ).derive_phc_encoded(value)


def screen_password(password: str, *, context: list[str] | None = None) -> None:
    """Reject readily guessed passwords locally, without a breach lookup service."""
    from zxcvbn import zxcvbn

    _password_bytes(password, creating=True)
    with _hashing_slot():
        result = zxcvbn(password, user_inputs=context or [], max_length=MAX_CHARACTERS)
    if result["score"] < 3:
        raise ServiceError(
            422,
            "weak_password",
            "Choose a less predictable password, such as several unrelated words.",
        )


def verify_password(password: str, encoded: str | None) -> bool:
    """Use None for an unknown account; missing/invalid verifiers never succeed.

    This uses the library's constant-time verifier, including a dummy check for
    unknown accounts. It does not claim the surrounding database or HTTP login
    path has identical timing; that path still needs bounded attempt throttling.
    """
    try:
        value = _password_bytes(password, creating=False)
    except ServiceError:
        return False
    approved = _approved_hash(encoded)
    with _hashing_slot():
        try:
            Argon2id.verify_phc_encoded(value, encoded if approved else _DUMMY)
        except InvalidKey:
            return False
    return approved
