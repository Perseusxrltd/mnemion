"""Portable service entry point used by Studio's managed local workspace."""

import multiprocessing
import os


if __name__ == "__main__":
    # Mnemion uses modern OpenSSL algorithms. Never load optional legacy
    # providers from the build host or a user's unrelated OpenSSL installation.
    # Set this before cryptography (or a dispatched worker) can initialize.
    os.environ["CRYPTOGRAPHY_OPENSSL_NO_LEGACY"] = "1"
    # PyInstaller's child-process dispatch must run before importing the server.
    multiprocessing.freeze_support()
    from mnemion.service.cli import main

    raise SystemExit(main())
