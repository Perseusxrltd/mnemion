"""Filesystem arguments for native tools with legacy Windows path limits."""

import ntpath
import os
from pathlib import Path


def file_argument(path: Path) -> str:
    """Use an absolute extended-length path for Windows file arguments only.

    PostgreSQL's Windows client tools still reject conventional paths at 260
    characters. Prefixing their input/output files works without changing the
    machine's registry or moving private working files outside their owner.
    """
    value = os.fspath(path)
    if os.name != "nt":
        return value
    value = ntpath.normpath(ntpath.abspath(value))
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value
