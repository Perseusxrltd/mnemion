"""Database tools receive only their documented process and libpq settings."""

import os

import pytest

from mnemion.service import recovery


def test_backup_tools_drop_unrelated_credentials_and_keep_database_overrides(monkeypatch):
    inherited = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": "/fixture/home",
        "SystemRoot": "C:\\Windows",
        "TEMP": "/fixture/tmp",
        "LANG": "C.UTF-8",
        "PGHOST": "inherited.example.invalid",
        "PGPASSWORD": "inherited-database-fixture",
        "PGSERVICEFILE": "/fixture/pg_service.conf",
        "PGSSLMODE": "verify-full",
        "PGSSLMINPROTOCOLVERSION": "TLSv1.3",
        "PGREQUIREAUTH": "scram-sha-256",
        "PGSSLNEGOTIATION": "postgres",
        "PG_UNRELATED_SECRET": "fixture-unrelated-pg-value",
        "KRB5CCNAME": "FILE:/fixture/krb-cache",
        "MNEMION_VAULT_KEY": "fixture-vault-value",
        "MNEMION_BACKUP_KEY": "fixture-backup-value",
        "UNRELATED_SECRET": "fixture-unrelated-value",
        "AZURE_API_KEY": "fixture-provider-value",
        "PYTHONPATH": "/fixture/unrelated-python",
    }
    monkeypatch.setattr(recovery.os, "environ", inherited)
    actual = recovery._pg_environment("dbname=fixture user=reader password=database-only")
    assert actual["PGDATABASE"] == "fixture" and actual["PGUSER"] == "reader"
    assert actual["PGPASSWORD"] == "database-only" and actual["PGCONNECT_TIMEOUT"] == "10"
    for name in (
        "PATH",
        "HOME",
        "TEMP",
        "LANG",
        "PGHOST",
        "PGSERVICEFILE",
        "PGSSLMODE",
        "KRB5CCNAME",
        "PGSSLMINPROTOCOLVERSION",
        "PGREQUIREAUTH",
        "PGSSLNEGOTIATION",
    ):
        assert actual[name] == inherited[name]
    assert not any(
        name in actual
        for name in (
            "MNEMION_VAULT_KEY",
            "MNEMION_BACKUP_KEY",
            "UNRELATED_SECRET",
            "AZURE_API_KEY",
            "PYTHONPATH",
            "PG_UNRELATED_SECRET",
        )
    )


def test_backup_connection_keeps_explicit_tls_and_passfile_paths(monkeypatch):
    monkeypatch.setenv("PGSSLROOTCERT", "/fixture/old-root.pem")
    actual = recovery._pg_environment(
        "dbname=fixture sslmode=verify-full host=db.example.invalid "
        "sslrootcert='/fixture/certificate root.pem' passfile='/fixture/private passfile'"
    )
    assert actual["PGSSLMODE"] == "verify-full"
    assert actual["PGSSLROOTCERT"] == "/fixture/certificate root.pem"
    assert actual["PGPASSFILE"] == "/fixture/private passfile"


def test_backup_child_receives_no_unrelated_secrets_or_command_line_password(monkeypatch):
    monkeypatch.setenv("UNRELATED_SECRET", "fixture-unrelated-value")
    observed = {}

    class Process:
        def __init__(self, args, **kwargs):
            observed.update(args=args, **kwargs)

        def wait(self, *, timeout):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(recovery.subprocess, "Popen", Process)
    monkeypatch.setattr(recovery, "_pg_tool", lambda *args: "/fixture/pg_dump")
    recovery._run_pg("pg_dump", "dbname=fixture password=database-only", ["--format=custom"], None)
    assert observed["env"]["PGPASSWORD"] == "database-only"
    assert "UNRELATED_SECRET" not in observed["env"]
    assert "database-only" not in repr(observed["args"])
    assert observed["stderr"] == recovery.subprocess.DEVNULL


@pytest.mark.parametrize(
    "dsn", ["invalid_fixture_secret=value", "password='unterminated_fixture_secret"]
)
def test_invalid_connection_diagnostics_do_not_reflect_input(dsn):
    with pytest.raises(ValueError) as error:
        recovery._pg_environment(dsn)
    assert "fixture_secret" not in str(error.value)
