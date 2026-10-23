"""Mnemion: shared memory infrastructure with optional private legacy profiles."""

import os
import platform

from .version import __version__  # noqa: E402

# ONNX Runtime's CoreML provider segfaults during vector queries on Apple Silicon.
# Force CPU execution unless the user has explicitly set a preference.
if platform.machine() == "arm64" and platform.system() == "Darwin":
    os.environ.setdefault("ORT_DISABLE_COREML", "1")

__all__ = ["main", "__version__"]


def main(*args, **kwargs):
    """Retain the historical entry point without loading the CLI in every client."""
    from .cli import main as cli_main

    return cli_main(*args, **kwargs)
