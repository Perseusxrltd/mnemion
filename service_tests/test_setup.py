import json
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.cli import main
from mnemion.service.db import Database


def test_bootstrap_rolls_back_if_secret_cannot_be_persisted(postgres):
    name = "Failed setup " + uuid4().hex

    def fail(_):
        raise OSError("Disk full")

    with pytest.raises(OSError):
        bootstrap_tenant(
            postgres[0], tenant_name=name, administrator_name="Owner", credentials_sink=fail
        )
    with psycopg.connect(postgres[0]) as conn:
        assert (
            conn.execute("SELECT count(*) FROM mnemion.tenants WHERE name=%s", (name,)).fetchone()[
                0
            ]
            == 0
        )


def test_setup_cli_produces_separate_non_owner_logins_and_private_owner_key(
    postgres, monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("MNEMION_ADMIN_DATABASE_URL", postgres[0])
    prefix = "setup_" + uuid4().hex[:16]
    db_file, owner_file = tmp_path / "database.json", tmp_path / "owner.json"
    try:
        main(["logins", "--prefix", prefix, "--output", str(db_file)])
        credentials = json.loads(db_file.read_text())
        main(
            ["bootstrap", "--tenant", "CLI setup", "--owner", "Owner", "--output", str(owner_file)]
        )
        owner = json.loads(owner_file.read_text())
        if os.name != "nt":
            assert owner_file.stat().st_mode & 0o777 == 0o600
            assert db_file.stat().st_mode & 0o777 == 0o600
        assert owner["api_key"] not in capsys.readouterr().out
        app = Database(credentials["database_url"])
        worker = Database(credentials["worker_database_url"], worker=True)
        try:
            app.open()
            worker.open()
            assert str(app.authenticate(owner["api_key"]).principal_id) == owner["principal_id"]
        finally:
            app.close()
            worker.close()
        with pytest.raises(FileExistsError):
            main(
                [
                    "bootstrap",
                    "--tenant",
                    "Duplicate setup",
                    "--owner",
                    "Owner",
                    "--output",
                    str(owner_file),
                ]
            )
    finally:
        with psycopg.connect(postgres[0]) as conn:
            for suffix in ("api_login", "worker_login"):
                conn.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(prefix + "_" + suffix))
                )
