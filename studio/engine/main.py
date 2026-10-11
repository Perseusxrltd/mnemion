"""Portable service entry point used by Studio's managed local workspace."""

import multiprocessing


if __name__ == "__main__":
    # PyInstaller's child-process dispatch must run before importing the server.
    multiprocessing.freeze_support()
    from mnemion.service.cli import main

    raise SystemExit(main())
