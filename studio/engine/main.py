"""Portable service entry point used by Studio's managed local workspace."""

import multiprocessing
import os


if __name__ == "__main__":
    # Mnemion uses modern authenticated encryption/signatures. Frozen macOS
    # runtimes need not load OpenSSL's optional legacy-algorithm module.
    os.environ["CRYPTOGRAPHY_OPENSSL_NO_LEGACY"] = "1"
    # PyInstaller's child-process dispatch must run before importing the server.
    multiprocessing.freeze_support()
    from mnemion.service.cli import main

    raise SystemExit(main())
