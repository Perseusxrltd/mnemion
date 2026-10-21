"""Migration 033 pins existing grants without changing consent or custody data."""

from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from mnemion.capture_policy import CapturePolicy
from mnemion.service import db
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.identity import IdentityService
from mnemion.service.models import KeyInput, PrincipalInput
from service_tests.conftest import FixtureEmbedder


def test_existing_capture_grants_pin_the_exact_original_policy(postgres, tmp_path, monkeypatch):
    previous = tmp_path / "previous-service"
    scripts = previous / "migrations"
    scripts.mkdir(parents=True)
    newer = []
    for path in db.files("mnemion.service").joinpath("migrations").iterdir():
        if path.suffix == ".sql" and int(path.name[:3]) <= 32:
            (scripts / path.name).write_bytes(path.read_bytes())
        elif path.suffix == ".sql":
            newer.append(path.name)
    name = "capture_policy_upgrade_" + uuid4().hex
    admin_dsn, app_dsn = (make_conninfo(value, dbname=name) for value in postgres[:2])
    with psycopg.connect(postgres[0], autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    database = None
    try:
        with monkeypatch.context() as old:
            old.setattr(db, "files", lambda _: previous)
            assert len(db.migrate(admin_dsn)) == 32
            setup = bootstrap_tenant(
                admin_dsn,
                tenant_name="Capture policy upgrade",
                administrator_name="Owner",
                generation=FixtureEmbedder.generation,
            )
            database = db.Database(app_dsn)
            database.open()
            owner = database.authenticate(setup["api_key"])
            identity = IdentityService(database)
            principal = identity.create_principal(
                owner, PrincipalInput(name="Existing collector", kind="application")
            )
            key = identity.create_key(
                owner, UUID(principal["id"]), KeyInput(name="Original device key")
            )
            connector = uuid4()
            with psycopg.connect(admin_dsn) as conn:
                conn.execute(
                    """INSERT INTO mnemion.connectors(tenant_id,id,name,provider,principal_id,access_mode)
                                VALUES(%s,%s,'Existing capture','conversations',%s,'published')""",
                    (owner.tenant_id, connector, principal["id"]),
                )
                approved = CapturePolicy(
                    preset="selected",
                    capture_mode="messages",
                    include=["work/*.jsonl"],
                    retention="until_deleted",
                )
                for index, (mode, policy) in enumerate(
                    (
                        ("messages", None),
                        ("complete", None),
                        ("messages", approved.model_dump(mode="json")),
                    )
                ):
                    source, space, grant = uuid4(), uuid4(), uuid4()
                    conn.execute(
                        "INSERT INTO mnemion.spaces(tenant_id,id,name) VALUES(%s,%s,'Existing capture room')",
                        (owner.tenant_id, space),
                    )
                    conn.execute(
                        """INSERT INTO mnemion.capture_sources(tenant_id,source_id,connector_id,space_id,
                                      namespace,name,members,capture_mode,version,capture_policy)
                                    VALUES(%s,%s,%s,%s,'original-namespace','Existing source','{}',%s,7,%s)""",
                        (
                            owner.tenant_id,
                            source,
                            connector,
                            space,
                            mode,
                            Jsonb(policy) if policy else None,
                        ),
                    )
                    conn.execute(
                        """INSERT INTO mnemion.capture_grants(tenant_id,grant_id,source_id,device_key_id,revoked_at)
                                    VALUES(%s,%s,%s,%s,CASE WHEN %s THEN now() ELSE NULL END)""",
                        (owner.tenant_id, grant, source, key["id"], index == 1),
                    )
                    conn.execute(
                        "INSERT INTO mnemion.capture_denials(tenant_id,source_id,lineage_id) VALUES(%s,%s,%s)",
                        (owner.tenant_id, source, str(index) * 64),
                    )
                before = {}
                for table in ("capture_sources", "capture_grants", "capture_denials", "api_keys"):
                    before[table] = conn.execute(
                        sql.SQL(
                            "SELECT to_jsonb(t) FROM mnemion.{} t ORDER BY to_jsonb(t)::text"
                        ).format(sql.Identifier(table))
                    ).fetchall()
            database.close()
            database = None
        assert db.migrate(admin_dsn) == sorted(newer)
        assert db.migrate(admin_dsn) == []
        with psycopg.connect(admin_dsn) as conn:
            for table, original in before.items():
                field = (
                    sql.SQL("to_jsonb(t) - 'policy_version'")
                    if table in {"capture_sources", "capture_grants"}
                    else sql.SQL("to_jsonb(t)")
                )
                after = conn.execute(
                    sql.SQL("SELECT {} FROM mnemion.{} t ORDER BY ({})::text").format(
                        field, sql.Identifier(table), field
                    )
                ).fetchall()
                assert after == original
            rows = conn.execute("""SELECT s.policy_version,g.policy_version,v.policy_version,
                                            s.capture_mode=v.capture_mode,s.capture_policy IS NOT DISTINCT FROM v.capture_policy,
                                            s.created_at=v.created_at,v.transition_id,v.request_hash,v.previous_grants
                                     FROM mnemion.capture_sources s JOIN mnemion.capture_grants g USING(tenant_id,source_id)
                                       JOIN mnemion.capture_policy_versions v ON v.tenant_id=s.tenant_id AND v.source_id=s.source_id""").fetchall()
            assert len(rows) == 3
            assert all(row == (1, 1, 1, True, True, True, None, None, None) for row in rows)
        database = db.Database(app_dsn)
        database.open()
        assert database.authenticate(key["api_key"]).principal_id == UUID(principal["id"])
    finally:
        if database:
            database.close()
        with psycopg.connect(postgres[0], autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
