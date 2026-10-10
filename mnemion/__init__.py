"""Mnemion: shared memory infrastructure with optional private legacy profiles."""

import logging
import os
import platform

from .version import __version__  # noqa: E402

# ChromaDB 0.6.x ships a Posthog telemetry client whose capture() signature is
# incompatible with the bundled posthog library, producing noisy stderr warnings
# on every client operation ("Failed to send telemetry event … capture() takes
# 1 positional argument but 3 were given").  Silence just that logger.
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

# ONNX Runtime's CoreML provider segfaults during vector queries on Apple Silicon.
# Force CPU execution unless the user has explicitly set a preference.
if platform.machine() == "arm64" and platform.system() == "Darwin":
    os.environ.setdefault("ORT_DISABLE_COREML", "1")

__all__ = ["main", "__version__"]


def main(*args, **kwargs):
    """Retain the historical entry point without loading the CLI in every client."""
    from .cli import main as cli_main

    return cli_main(*args, **kwargs)
