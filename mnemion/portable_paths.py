"""One path identity across Windows, macOS, and Linux filesystems."""

import re
import unicodedata

DEVICES = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.IGNORECASE)


def path_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def portable_part(value: str) -> bool:
    return (
        bool(value)
        and value not in {".", ".."}
        and not (
            value != value.rstrip(" .")
            or DEVICES.match(value)
            or any(ord(c) < 32 or c in '<>:"|?*\\' for c in value)
        )
    )
