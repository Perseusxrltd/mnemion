"""New inventory execution must retain the previously released backup hashes."""

import hashlib
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from mnemion.service import recovery
from mnemion.service.models import MemoryInput


def released_inventory(conn, version):
    """The v4.46.3 query is an oracle for existing off-host backup manifests."""
    result = {}
    tables = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='mnemion' ORDER BY tablename"
    ).fetchall()
    for entry in tables:
        table = entry["tablename"]
        projection = sql.SQL("to_jsonb(t)")
        if table == "memory_revisions" and version == 2:
            projection = sql.SQL("to_jsonb(t) - 'search_text'")
        rows = conn.execute(
            sql.SQL(
                'SELECT ({})::text AS row FROM mnemion.{} t ORDER BY ({})::text COLLATE "C"'
            ).format(projection, sql.Identifier(table), projection)
        ).fetchall()
        digest = hashlib.sha256()
        for row in rows:
            digest.update(row["row"].encode() + b"\n")
        result[table] = {"count": len(rows), "sha256": digest.hexdigest()}
    return result


def test_released_v1_and_v2_inventory_hashes_survive_query_optimization(env):
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content='Résumé: unicode, "quotes", backslash \\ and\nnewlines.'),
        "inventory-compatibility",
    )
    table = sql.Identifier("inventory_compatibility_" + uuid4().hex)
    with psycopg.connect(env.admin_dsn, row_factory=dict_row) as conn:
        conn.execute("SET LOCAL timezone='UTC'")
        # Future tables, NULLs and duplicate rows must remain covered without
        # relying on primary-key shape or a different numeric ordering.
        conn.execute(
            sql.SQL("CREATE TABLE mnemion.{} (number numeric, label text, payload jsonb)").format(
                table
            )
        )
        for number in (None, "-10", "-1", "1", "1.0", "1.01", "10", "100"):
            for label in (None, "", "é", "α", 'line\n"quote"', "🧠"):
                conn.execute(
                    sql.SQL("INSERT INTO mnemion.{} VALUES (%s,%s,%s::jsonb)").format(table),
                    (number, label, '{"nested":[1,null,"text"]}'),
                )
        conn.execute(
            sql.SQL("INSERT INTO mnemion.{} SELECT * FROM mnemion.{}").format(table, table)
        )
        for version in (1, 2):
            expected = released_inventory(conn, version)
            assert recovery.inventory(conn, version=version) == expected
        conn.rollback()
