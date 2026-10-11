"""Current-user Windows DPAPI for the desktop's private credential pipe.

Unlike Chromium's profile key, DPAPI has no deferred application key file that
can be lost when a new profile is terminated before its preferences are saved.
Inputs and results travel over the packaged client's pipes, never arguments.
"""

import base64
import ctypes
import json
import sys

_PREFIX = b"MNMDPAPI\x01"
_ENTROPY = b"com.perseusxr.mnemion-studio/workspace-key/v1"
_MAX_PLAIN = 8192
_MAX_SEALED = 16384


def _dpapi(value: bytes, *, protect: bool) -> bytes:
    if sys.platform != "win32":
        raise ValueError("Windows credential protection is only available on Windows.")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    source_buffer = ctypes.create_string_buffer(value)
    entropy_buffer = ctypes.create_string_buffer(_ENTROPY)
    source = Blob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    entropy = Blob(len(_ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    function = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        wintypes.LPCWSTR if protect else ctypes.c_void_p,
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    try:
        # CRYPTPROTECT_UI_FORBIDDEN; deliberately omit LOCAL_MACHINE so another
        # Windows account cannot decrypt a copied workspace credential.
        if not function(
            ctypes.byref(source),
            "Mnemion workspace" if protect else None,
            ctypes.byref(entropy),
            None,
            None,
            1,
            ctypes.byref(output),
        ):
            raise ValueError("Windows could not protect or unlock this saved connection.")
        if not output.data or output.size > _MAX_SEALED:
            raise ValueError("Invalid Windows credential result.")
        return ctypes.string_at(output.data, output.size)
    finally:
        if output.data:
            # Zero the native output before releasing the OS allocation.
            ctypes.memset(output.data, 0, output.size)
            kernel.LocalFree(output.data)
        ctypes.memset(source_buffer, 0, len(source_buffer))
        ctypes.memset(entropy_buffer, 0, len(entropy_buffer))


def credential_request(operation: str, request: bytes) -> dict[str, str]:
    if len(request) > 24576:
        raise ValueError("Credential request is too large.")
    try:
        document = json.loads(request)
    except (ValueError, UnicodeError):
        raise ValueError("Invalid credential request.") from None
    if not isinstance(document, dict) or set(document) != {"value"}:
        raise ValueError("Invalid credential request.")
    value = document["value"]
    if not isinstance(value, str) or not value:
        raise ValueError("Invalid credential value.")
    if operation == "protect":
        try:
            encoded = value.encode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid credential value.") from None
        if len(encoded) > _MAX_PLAIN:
            raise ValueError("Credential value is too large.")
        result = base64.b64encode(_PREFIX + _dpapi(encoded, protect=True)).decode("ascii")
    elif operation == "unprotect":
        if len(value) > _MAX_SEALED:
            raise ValueError("Protected credential is too large.")
        try:
            encoded = base64.b64decode(value, validate=True)
        except (ValueError, UnicodeError):
            raise ValueError("Invalid protected credential.") from None
        if not encoded.startswith(_PREFIX):
            raise ValueError("Reconnect with your key to replace this saved connection.")
        plain = _dpapi(encoded[len(_PREFIX) :], protect=False)
        if len(plain) > _MAX_PLAIN:
            raise ValueError("Invalid protected credential.")
        try:
            result = plain.decode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid protected credential.") from None
    else:
        raise ValueError("Unknown credential operation.")
    return {"value": result}
