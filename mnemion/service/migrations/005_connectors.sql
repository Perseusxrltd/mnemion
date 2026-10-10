-- Managed provider scopes reuse the same RLS boundary as all memory transports.
-- Connector identities can manage only the spaces belonging to their connection.
CREATE TABLE mnemion.connectors (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    name text NOT NULL,
    provider text NOT NULL,
    principal_id uuid NOT NULL,
    access_mode text NOT NULL CHECK (access_mode IN ('provider','published')),
    disabled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,id),
    UNIQUE (tenant_id,principal_id),
    FOREIGN KEY (tenant_id,principal_id) REFERENCES mnemion.principals(tenant_id,id)
);
CREATE TABLE mnemion.connector_bindings (
    tenant_id uuid NOT NULL,
    connector_id uuid NOT NULL,
    external_id text NOT NULL,
    principal_id uuid NOT NULL,
    role text NOT NULL CHECK (role IN ('reader','reviewer')),
    PRIMARY KEY (tenant_id,connector_id,external_id,principal_id),
    FOREIGN KEY (tenant_id,connector_id) REFERENCES mnemion.connectors(tenant_id,id),
    FOREIGN KEY (tenant_id,principal_id) REFERENCES mnemion.principals(tenant_id,id)
);
CREATE TABLE mnemion.connector_scopes (
    tenant_id uuid NOT NULL,
    connector_id uuid NOT NULL,
    space_id uuid NOT NULL,
    external_id text NOT NULL,
    observed_at timestamptz NOT NULL,
    access_valid_until timestamptz NOT NULL,
    suspended_at timestamptz,
    suspension_reason text,
    checkpoint text,
    completed_at timestamptz,
    PRIMARY KEY (tenant_id,space_id),
    UNIQUE (tenant_id,connector_id,external_id),
    FOREIGN KEY (tenant_id,connector_id) REFERENCES mnemion.connectors(tenant_id,id),
    FOREIGN KEY (tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id)
);
CREATE TABLE mnemion.connector_members (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    external_id text NOT NULL,
    PRIMARY KEY (tenant_id,space_id,external_id),
    FOREIGN KEY (tenant_id,space_id) REFERENCES mnemion.connector_scopes(tenant_id,space_id)
);
CREATE TABLE mnemion.connector_runs (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    mode text NOT NULL CHECK(mode IN ('snapshot','incremental')),
    state text NOT NULL DEFAULT 'running' CHECK(state IN ('running','finalizing','completed','aborted')),
    next_sequence integer NOT NULL DEFAULT 0,
    checkpoint text,
    lease_until timestamptz NOT NULL DEFAULT now()+interval '5 minutes',
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    result jsonb,
    PRIMARY KEY (tenant_id,space_id,id),
    FOREIGN KEY (tenant_id,space_id) REFERENCES mnemion.connector_scopes(tenant_id,space_id)
);
CREATE UNIQUE INDEX connector_one_run ON mnemion.connector_runs(tenant_id,space_id)
    WHERE state IN ('running','finalizing');
CREATE TABLE mnemion.connector_pages (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    run_id uuid NOT NULL,
    sequence integer NOT NULL,
    request_hash text NOT NULL,
    response jsonb NOT NULL,
    PRIMARY KEY(tenant_id,space_id,run_id,sequence),
    FOREIGN KEY(tenant_id,space_id,run_id) REFERENCES mnemion.connector_runs(tenant_id,space_id,id)
);
CREATE TABLE mnemion.connector_items (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    external_id text NOT NULL,
    memory_id uuid,
    origin_revision text NOT NULL,
    content_hash text,
    applied_version integer,
    last_seen_run uuid NOT NULL,
    state text NOT NULL CHECK(state IN ('active','deleted','conflict')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,space_id,external_id),
    UNIQUE(tenant_id,space_id,memory_id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.connector_scopes(tenant_id,space_id),
    FOREIGN KEY(tenant_id,space_id,memory_id) REFERENCES mnemion.memories(tenant_id,space_id,id)
);
CREATE TABLE mnemion.connector_proposals (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    proposal_hash text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,space_id,memory_id),
    FOREIGN KEY(tenant_id,space_id,memory_id) REFERENCES mnemion.connector_items(tenant_id,space_id,memory_id)
);

CREATE FUNCTION mnemion.owns_connector(connection uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.connectors c JOIN mnemion.principals p
        ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
        WHERE c.tenant_id=mnemion.tenant() AND c.id=connection
          AND c.principal_id=mnemion.principal() AND c.disabled_at IS NULL
          AND p.disabled_at IS NULL AND NOT p.administrator)
$$;
CREATE FUNCTION mnemion.owns_connector_scope(space uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.connector_scopes s
        WHERE s.tenant_id=mnemion.tenant() AND s.space_id=space
          AND mnemion.owns_connector(s.connector_id))
$$;
CREATE FUNCTION mnemion.managed_scope(space uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.connector_scopes s
        WHERE s.tenant_id=mnemion.tenant() AND s.space_id=space)
$$;
CREATE OR REPLACE FUNCTION mnemion.authorized(space uuid, level integer DEFAULT 10) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS (
        SELECT FROM mnemion.space_grants g JOIN mnemion.principals p
          ON p.tenant_id=g.tenant_id AND p.id=g.principal_id
        LEFT JOIN mnemion.connector_scopes s ON s.tenant_id=g.tenant_id AND s.space_id=g.space_id
        LEFT JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
        LEFT JOIN mnemion.principals cp ON cp.tenant_id=c.tenant_id AND cp.id=c.principal_id
        WHERE g.tenant_id=mnemion.tenant() AND g.space_id=space
          AND g.principal_id=mnemion.principal() AND p.disabled_at IS NULL
          AND CASE g.role WHEN 'reader' THEN 10 WHEN 'contributor' THEN 20
              WHEN 'reviewer' THEN 30 WHEN 'administrator' THEN 40 END >= level
          AND (s.space_id IS NULL OR (c.disabled_at IS NULL AND cp.disabled_at IS NULL AND NOT cp.administrator AND (
              (c.principal_id=mnemion.principal() AND NOT p.administrator)
              OR (s.suspended_at IS NULL AND s.access_valid_until>now()))))
    )
$$;
-- Only these narrow functions create and renew managed access. Ordinary grant
-- mutations cannot override the provider's access ceiling, including for admins.
DROP POLICY grant_scope ON mnemion.space_grants;
CREATE POLICY grant_read ON mnemion.space_grants FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (principal_id=mnemion.principal()
      OR mnemion.administrator() OR mnemion.authorized(space_id,40)));
CREATE POLICY grant_write ON mnemion.space_grants FOR ALL TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND NOT mnemion.managed_scope(space_id)
      AND (mnemion.administrator() OR mnemion.authorized(space_id,40)))
    WITH CHECK (tenant_id=mnemion.tenant() AND NOT mnemion.managed_scope(space_id)
      AND (mnemion.administrator() OR mnemion.authorized(space_id,40)));

CREATE FUNCTION mnemion.refresh_connector_scope(connection uuid, external text, label text,
    members text[], observed timestamptz, seconds integer) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE space uuid;
BEGIN
    IF NOT mnemion.owns_connector(connection) THEN RAISE insufficient_privilege; END IF;
    IF length(external) NOT BETWEEN 1 AND 512 OR length(label) NOT BETWEEN 1 AND 200
       OR cardinality(members)>10000 OR seconds NOT BETWEEN 60 AND 86400
       OR observed>now()+interval '30 seconds' OR observed+make_interval(secs=>seconds)<=now()
    THEN RAISE invalid_parameter_value; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(mnemion.tenant()::text||connection::text||external,0));
    SELECT space_id INTO space FROM mnemion.connector_scopes
      WHERE tenant_id=mnemion.tenant() AND connector_id=connection AND external_id=external;
    IF space IS NULL THEN
        space:=gen_random_uuid();
        INSERT INTO mnemion.spaces(tenant_id,id,name,description)
          VALUES(mnemion.tenant(),space,label,'Managed source permissions');
        INSERT INTO mnemion.connector_scopes(tenant_id,connector_id,space_id,external_id,observed_at,access_valid_until)
          VALUES(mnemion.tenant(),connection,space,external,observed,observed+make_interval(secs=>seconds));
    ELSIF EXISTS(SELECT FROM mnemion.connector_scopes WHERE tenant_id=mnemion.tenant()
                 AND space_id=space AND observed_at>observed) THEN
        RAISE EXCEPTION 'Older access snapshot' USING ERRCODE='22023';
    END IF;
    -- Serialize access changes with canonical connector writes and finalization.
    PERFORM pg_advisory_xact_lock(hashtextextended('connector:'||space::text,0));
    UPDATE mnemion.spaces SET name=label WHERE tenant_id=mnemion.tenant() AND id=space;
    DELETE FROM mnemion.connector_members WHERE tenant_id=mnemion.tenant() AND space_id=space;
    INSERT INTO mnemion.connector_members(tenant_id,space_id,external_id)
      SELECT DISTINCT mnemion.tenant(),space,unnest(members);
    DELETE FROM mnemion.space_grants WHERE tenant_id=mnemion.tenant() AND space_id=space;
    INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role)
      SELECT mnemion.tenant(),space,b.principal_id,
        CASE WHEN bool_or(b.role='reviewer') THEN 'reviewer' ELSE 'reader' END
      FROM mnemion.connector_bindings b
      WHERE b.tenant_id=mnemion.tenant() AND b.connector_id=connection AND b.external_id=ANY(members)
        AND b.principal_id<>mnemion.principal()
      GROUP BY b.principal_id;
    INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role)
      VALUES(mnemion.tenant(),space,mnemion.principal(),'administrator');
    UPDATE mnemion.connector_scopes SET observed_at=observed,
      access_valid_until=observed+make_interval(secs=>seconds),suspended_at=NULL,suspension_reason=NULL
      WHERE tenant_id=mnemion.tenant() AND space_id=space;
    RETURN space;
END
$$;
CREATE FUNCTION mnemion.suspend_connector_scope(space uuid, reason text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NOT (mnemion.owns_connector_scope(space) OR (mnemion.administrator()
        AND mnemion.managed_scope(space))) THEN RAISE insufficient_privilege; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('connector:'||space::text,0));
    UPDATE mnemion.connector_scopes SET suspended_at=now(),suspension_reason=reason,
      access_valid_until=least(access_valid_until,now()) WHERE tenant_id=mnemion.tenant() AND space_id=space;
    UPDATE mnemion.connector_runs SET state='aborted',finished_at=now()
      WHERE tenant_id=mnemion.tenant() AND space_id=space AND state IN ('running','finalizing');
END
$$;
CREATE FUNCTION mnemion.commit_connector_cursor(space uuid, cursor_value text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NOT mnemion.owns_connector_scope(space) THEN RAISE insufficient_privilege; END IF;
    UPDATE mnemion.connector_scopes SET checkpoint=cursor_value,completed_at=now()
      WHERE tenant_id=mnemion.tenant() AND space_id=space;
END
$$;
-- Changing identity mappings revokes existing derived grants immediately. New
-- grants require a fresh provider permission snapshot, rather than stale members.
CREATE FUNCTION mnemion.binding_changed() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE connection uuid; tenant uuid;
BEGIN
    connection:=coalesce(NEW.connector_id,OLD.connector_id);
    tenant:=coalesce(NEW.tenant_id,OLD.tenant_id);
    UPDATE mnemion.connector_scopes SET suspended_at=now(),
      suspension_reason='identity_mapping_changed',access_valid_until=least(access_valid_until,now())
      WHERE tenant_id=tenant AND connector_id=connection;
    UPDATE mnemion.connector_runs SET state='aborted',finished_at=now()
      WHERE tenant_id=tenant AND state IN ('running','finalizing') AND space_id IN
        (SELECT space_id FROM mnemion.connector_scopes WHERE tenant_id=tenant AND connector_id=connection);
    RETURN coalesce(NEW,OLD);
END
$$;
CREATE TRIGGER connector_binding_changed AFTER INSERT OR UPDATE OR DELETE ON mnemion.connector_bindings
    FOR EACH ROW EXECUTE FUNCTION mnemion.binding_changed();

ALTER TABLE mnemion.connectors ENABLE ROW LEVEL SECURITY;
CREATE POLICY connector_read ON mnemion.connectors FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR principal_id=mnemion.principal()));
CREATE POLICY connector_write ON mnemion.connectors FOR ALL TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.administrator())
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.administrator());
ALTER TABLE mnemion.connector_bindings ENABLE ROW LEVEL SECURITY;
CREATE POLICY binding_read ON mnemion.connector_bindings FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_connector(connector_id)));
CREATE POLICY binding_write ON mnemion.connector_bindings FOR ALL TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.administrator())
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.administrator());
ALTER TABLE mnemion.connector_scopes ENABLE ROW LEVEL SECURITY;
CREATE POLICY scope_read ON mnemion.connector_scopes FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_connector(connector_id)));
ALTER TABLE mnemion.connector_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY member_read ON mnemion.connector_members FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_connector_scope(space_id)));
DO $policies$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['connector_runs','connector_pages','connector_items'] LOOP
        EXECUTE format('ALTER TABLE mnemion.%I ENABLE ROW LEVEL SECURITY',tab);
        EXECUTE format('CREATE POLICY connector_owned ON mnemion.%I TO mnemion_app USING
          (tenant_id=mnemion.tenant() AND mnemion.owns_connector_scope(space_id)) WITH CHECK
          (tenant_id=mnemion.tenant() AND mnemion.owns_connector_scope(space_id))',tab);
    END LOOP;
END
$policies$;
CREATE POLICY item_review ON mnemion.connector_items TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30))
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30));
CREATE POLICY run_admin_read ON mnemion.connector_runs FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.administrator());
ALTER TABLE mnemion.connector_proposals ENABLE ROW LEVEL SECURITY;
CREATE POLICY proposal_scope ON mnemion.connector_proposals TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30) AND EXISTS
      (SELECT FROM mnemion.memories m WHERE m.tenant_id=connector_proposals.tenant_id
        AND m.space_id=connector_proposals.space_id AND m.id=connector_proposals.memory_id AND m.deleted_at IS NULL))
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30));
CREATE POLICY proposal_worker ON mnemion.connector_proposals TO mnemion_worker
    USING(tenant_id=mnemion.tenant()) WITH CHECK(tenant_id=mnemion.tenant());
REVOKE ALL ON mnemion.connectors,mnemion.connector_bindings,mnemion.connector_scopes,
    mnemion.connector_members,mnemion.connector_runs,mnemion.connector_pages,
    mnemion.connector_items,mnemion.connector_proposals FROM mnemion_app,mnemion_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON mnemion.connectors,mnemion.connector_bindings,
    mnemion.connector_runs,mnemion.connector_pages,mnemion.connector_items,mnemion.connector_proposals TO mnemion_app;
GRANT SELECT ON mnemion.connector_scopes,mnemion.connector_members TO mnemion_app;
GRANT SELECT,DELETE ON mnemion.connector_proposals TO mnemion_worker;
REVOKE ALL ON FUNCTION mnemion.owns_connector(uuid),mnemion.owns_connector_scope(uuid),
    mnemion.managed_scope(uuid),mnemion.refresh_connector_scope(uuid,text,text,text[],timestamptz,integer),
    mnemion.suspend_connector_scope(uuid,text),mnemion.commit_connector_cursor(uuid,text),mnemion.binding_changed() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.owns_connector(uuid),mnemion.owns_connector_scope(uuid),
    mnemion.managed_scope(uuid) TO mnemion_app,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.refresh_connector_scope(uuid,text,text,text[],timestamptz,integer),
    mnemion.suspend_connector_scope(uuid,text),mnemion.commit_connector_cursor(uuid,text) TO mnemion_app;
