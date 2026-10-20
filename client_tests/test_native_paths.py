import os
from pathlib import Path
import subprocess

import pytest

from mnemion.native_paths import file_argument


def test_native_file_arguments_preserve_the_selected_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    relative = Path("Équipe") / ".." / "database.dump"
    if os.name != "nt":
        assert file_argument(relative) == str(relative)
        return
    assert file_argument(relative) == "\\\\?\\" + str(tmp_path / "database.dump")
    assert file_argument(Path(r"\\server\share\Équipe\..\database.dump")) == (
        r"\\?\UNC\server\share\database.dump"
    )
    extended = Path(r"\\?\C:\Équipe\database.dump")
    assert file_argument(extended) == str(extended)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows PostgreSQL file handling")
def test_windows_postgres_tools_open_long_backup_files(tmp_path):
    pg_bin = os.environ.get("MNEMION_PG_BIN")
    if not pg_bin:
        pytest.skip("Requires the bundled PostgreSQL tools via MNEMION_PG_BIN")
    # No workspace or running database is used. pg_dump opens its output before
    # attempting this bounded, deliberately unavailable loopback connection.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("PG", "MNEMION_"))
    }
    environment["LC_ALL"] = "C"
    parent = tmp_path / ("private-backup-" + "x" * 100)
    parent.mkdir()
    for length in (260, 320):
        name_length = length - len(str(parent)) - 1
        assert 1 <= name_length <= 255
        path = parent / ("d" * name_length)
        result = subprocess.run(
            [
                str(Path(pg_bin) / "pg_dump.exe"),
                "--format=custom",
                "--file=" + file_argument(path),
                "--dbname=host=127.0.0.1 port=1 user=synthetic dbname=synthetic "
                "connect_timeout=1 sslmode=disable",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0 and path.is_file()
        assert "could not open output file" not in result.stderr
        assert "connection to server" in result.stderr
        path.write_bytes(b"PGDMP\xff\xffsynthetic invalid archive")
        result = subprocess.run(
            [str(Path(pg_bin) / "pg_restore.exe"), "--list", file_argument(path)],
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0 and "unsupported version" in result.stderr
        assert "could not open input file" not in result.stderr
