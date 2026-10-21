-- Durable capture is explicitly consented custody, never a provider mirror.
-- Its spaces are deliberately absent from connector_scopes and its lease sweep.
CREATE TABLE mnemion.capture_sources (
    tenant_id uuid NOT NULL,
    source_id uuid NOT NULL,
    connector_id uuid NOT NULL,
    space_id uuid NOT NULL,
    namespace text NOT NULL CHECK(length(namespace) BETWEEN 1 AND 400),
    name text NOT NULL CHECK(length(name) BETWEEN 1 AND 200),
    members text[] NOT NULL CHECK(cardinality(members)<=128),
    capture_mode text NOT NULL CHECK(capture_mode IN ('messages','complete')),
    version integer NOT NULL DEFAULT 1 CHECK(version>=1),
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,source_id),
    UNIQUE(tenant_id,space_id),
    FOREIGN KEY(tenant_id,connector_id) REFERENCES mnemion.connectors(tenant_id,id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id)
);
CREATE TABLE mnemion.capture_grants (
    tenant_id uuid NOT NULL,
    grant_id uuid NOT NULL,
    source_id uuid NOT NULL,
    device_key_id uuid NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,grant_id),
    FOREIGN KEY(tenant_id,source_id) REFERENCES mnemion.capture_sources(tenant_id,source_id),
    FOREIGN KEY(tenant_id,device_key_id) REFERENCES mnemion.api_keys(tenant_id,id)
);
CREATE TABLE mnemion.capture_events (
    tenant_id uuid NOT NULL,
    source_id uuid NOT NULL,
    event_id text NOT NULL CHECK(event_id ~ '^[a-f0-9]{64}$'),
    producer_scope text NOT NULL,
    origin_external_id text NOT NULL,
    origin_revision text NOT NULL,
    lineage_id text NOT NULL CHECK(lineage_id ~ '^[a-f0-9]{64}$'),
    payload_hash text NOT NULL CHECK(payload_hash ~ '^[a-f0-9]{64}$'),
    space_id uuid NOT NULL,
    memory_id uuid,
    operation_id uuid,
    accepted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,source_id,event_id),
    UNIQUE(tenant_id,source_id,producer_scope,origin_external_id,origin_revision),
    UNIQUE(tenant_id,space_id,memory_id),
    FOREIGN KEY(tenant_id,source_id) REFERENCES mnemion.capture_sources(tenant_id,source_id),
    FOREIGN KEY(tenant_id,space_id,memory_id) REFERENCES mnemion.memories(tenant_id,space_id,id)
);
CREATE INDEX capture_event_lineage ON mnemion.capture_events(tenant_id,source_id,lineage_id);
CREATE INDEX capture_event_memory ON mnemion.capture_events(memory_id) WHERE memory_id IS NOT NULL;
CREATE TABLE mnemion.capture_pages (
    tenant_id uuid NOT NULL,
    grant_id uuid NOT NULL,
    page_id uuid NOT NULL,
    request_hash text NOT NULL,
    event_ids text[] NOT NULL CHECK(cardinality(event_ids) BETWEEN 1 AND 50),
    accepted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,grant_id,page_id),
    FOREIGN KEY(tenant_id,grant_id) REFERENCES mnemion.capture_grants(tenant_id,grant_id)
);
CREATE TABLE mnemion.capture_denials (
    tenant_id uuid NOT NULL,
    source_id uuid NOT NULL,
    lineage_id text NOT NULL CHECK(lineage_id ~ '^[a-f0-9]{64}$'),
    forgotten_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,source_id,lineage_id),
    FOREIGN KEY(tenant_id,source_id) REFERENCES mnemion.capture_sources(tenant_id,source_id)
);

CREATE FUNCTION mnemion.owns_capture_source(source uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.capture_sources s WHERE s.tenant_id=mnemion.tenant()
      AND s.source_id=source AND s.revoked_at IS NULL AND mnemion.owns_connector(s.connector_id))
$$;
-- Source administrators need a truthful migration guard even without content
-- access. Expose only this boolean under the source-policy read boundary;
-- event rows and memory content retain their separate, narrower permissions.
CREATE FUNCTION mnemion.capture_source_has_history(source uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.capture_sources s
      WHERE s.tenant_id=mnemion.tenant() AND s.source_id=source
        AND (mnemion.administrator() OR mnemion.owns_connector(s.connector_id))
        AND (EXISTS(SELECT FROM mnemion.capture_events e
          WHERE e.tenant_id=s.tenant_id AND e.source_id=s.source_id)
          OR EXISTS(SELECT FROM mnemion.capture_denials d
            WHERE d.tenant_id=s.tenant_id AND d.source_id=s.source_id)))
$$;
CREATE OR REPLACE FUNCTION mnemion.managed_scope(space uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.connector_scopes s
        WHERE s.tenant_id=mnemion.tenant() AND s.space_id=space)
      OR EXISTS(SELECT FROM mnemion.capture_sources s
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
        LEFT JOIN mnemion.capture_sources cs ON cs.tenant_id=g.tenant_id AND cs.space_id=g.space_id
        LEFT JOIN mnemion.connectors cc ON cc.tenant_id=cs.tenant_id AND cc.id=cs.connector_id
        LEFT JOIN mnemion.principals ccp ON ccp.tenant_id=cc.tenant_id AND ccp.id=cc.principal_id
        WHERE g.tenant_id=mnemion.tenant() AND g.space_id=space
          AND g.principal_id=mnemion.principal() AND p.disabled_at IS NULL
          AND CASE g.role WHEN 'reader' THEN 10 WHEN 'contributor' THEN 20
              WHEN 'reviewer' THEN 30 WHEN 'administrator' THEN 40 END >= level
          AND (s.space_id IS NULL OR (c.disabled_at IS NULL AND cp.disabled_at IS NULL AND NOT cp.administrator AND (
              (c.principal_id=mnemion.principal() AND NOT p.administrator)
              OR (s.suspended_at IS NULL AND s.access_valid_until>now()))))
          AND (cs.space_id IS NULL OR (cs.revoked_at IS NULL AND cc.disabled_at IS NULL
              AND ccp.disabled_at IS NULL AND NOT ccp.administrator
              AND (cc.principal_id=mnemion.principal() OR EXISTS(
                SELECT FROM mnemion.connector_bindings b WHERE b.tenant_id=cs.tenant_id
                  AND b.connector_id=cs.connector_id AND b.external_id=ANY(cs.members)
                  AND b.principal_id=mnemion.principal()
                  AND CASE b.role WHEN 'reviewer' THEN 30 ELSE 10 END >= level))))
    )
$$;

-- Custody revocation also stops background inference. Keep the independent
-- provider-lease checks for legacy source mirrors exactly as before.
CREATE OR REPLACE FUNCTION mnemion.embedding_source_current(space uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.spaces WHERE tenant_id=mnemion.tenant() AND id=space)
      AND NOT EXISTS(SELECT FROM mnemion.connector_scopes s
        JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
        JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
        WHERE s.tenant_id=mnemion.tenant() AND s.space_id=space
          AND (s.operator_paused OR s.suspended_at IS NOT NULL OR s.access_valid_until<=now()
               OR c.disabled_at IS NOT NULL OR p.disabled_at IS NOT NULL OR p.administrator))
      AND NOT EXISTS(SELECT FROM mnemion.capture_sources s
        JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
        JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
        WHERE s.tenant_id=mnemion.tenant() AND s.space_id=space
          AND (s.revoked_at IS NOT NULL OR c.disabled_at IS NOT NULL
               OR p.disabled_at IS NOT NULL OR p.administrator))
$$;

-- Only server-side administrator consent populates custody grants. Membership
-- changes immediately recompute those grants, without claiming provider access.
CREATE FUNCTION mnemion.refresh_capture_members(tenant_value uuid, source uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE row mnemion.capture_sources; operator uuid;
BEGIN
    SELECT * INTO row FROM mnemion.capture_sources
      WHERE tenant_id=tenant_value AND source_id=source;
    IF NOT FOUND THEN RETURN; END IF;
    SELECT principal_id INTO operator FROM mnemion.connectors
      WHERE tenant_id=row.tenant_id AND id=row.connector_id;
    DELETE FROM mnemion.space_grants WHERE tenant_id=row.tenant_id AND space_id=row.space_id;
    INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role)
      SELECT row.tenant_id,row.space_id,b.principal_id,
        CASE WHEN bool_or(b.role='reviewer') THEN 'reviewer' ELSE 'reader' END
      FROM mnemion.connector_bindings b
      WHERE b.tenant_id=row.tenant_id AND b.connector_id=row.connector_id
        AND b.external_id=ANY(row.members) AND b.principal_id<>operator GROUP BY b.principal_id;
    INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role)
      VALUES(row.tenant_id,row.space_id,operator,'administrator');
END
$$;
CREATE FUNCTION mnemion.capture_members_changed() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE source uuid; tenant_value uuid; connection uuid;
BEGIN
    tenant_value:=coalesce(NEW.tenant_id,OLD.tenant_id);
    connection:=coalesce(NEW.connector_id,OLD.connector_id);
    PERFORM pg_advisory_xact_lock(hashtextextended(
      'capture-members:'||tenant_value::text||':'||connection::text,0));
    IF TG_TABLE_NAME='capture_sources' THEN
        PERFORM mnemion.refresh_capture_members(NEW.tenant_id,NEW.source_id);
    ELSE
        FOR source IN SELECT source_id FROM mnemion.capture_sources
          WHERE tenant_id=tenant_value AND connector_id=connection
        LOOP PERFORM mnemion.refresh_capture_members(tenant_value,source); END LOOP;
    END IF;
    RETURN coalesce(NEW,OLD);
END
$$;
CREATE TRIGGER capture_source_members AFTER INSERT OR UPDATE OF members ON mnemion.capture_sources
    FOR EACH ROW EXECUTE FUNCTION mnemion.capture_members_changed();
CREATE TRIGGER capture_binding_members AFTER INSERT OR UPDATE OR DELETE ON mnemion.connector_bindings
    FOR EACH ROW EXECUTE FUNCTION mnemion.capture_members_changed();

-- The canonical memory deletion transaction creates the source denial too.
-- A narrow Python pre-lock uses this same source lock before locking the memory.
CREATE FUNCTION mnemion.capture_memory_forgotten() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
        INSERT INTO mnemion.capture_denials(tenant_id,source_id,lineage_id)
          SELECT tenant_id,source_id,lineage_id FROM mnemion.capture_events
            WHERE tenant_id=NEW.tenant_id AND space_id=NEW.space_id AND memory_id=NEW.id
          ON CONFLICT DO NOTHING;
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER capture_forget_fence AFTER UPDATE OF deleted_at ON mnemion.memories
    FOR EACH ROW EXECUTE FUNCTION mnemion.capture_memory_forgotten();

CREATE FUNCTION mnemion.revoke_capture_grant(grant_value uuid, key_value uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    UPDATE mnemion.capture_grants g SET revoked_at=coalesce(g.revoked_at,now())
      WHERE g.tenant_id=mnemion.tenant() AND g.grant_id=grant_value
        AND (mnemion.administrator() OR (g.device_key_id=key_value AND EXISTS(
          SELECT FROM mnemion.api_keys k WHERE k.tenant_id=g.tenant_id AND k.id=key_value
            AND k.principal_id=mnemion.principal())));
END
$$;

-- Lock authority rows through the page commit. Revoking a device key or its
-- connector must serialize with acceptance, including requests already queued.
-- Only the exact authenticated device can lock its own consented source.
CREATE FUNCTION mnemion.lock_capture_authority(grant_value uuid, key_value uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    PERFORM 1 FROM mnemion.capture_grants g
      JOIN mnemion.capture_sources s USING(tenant_id,source_id)
      JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
      JOIN mnemion.api_keys k ON k.tenant_id=g.tenant_id AND k.id=g.device_key_id
      JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
      WHERE g.tenant_id=mnemion.tenant() AND g.grant_id=grant_value
        AND g.device_key_id=key_value AND k.principal_id=mnemion.principal()
        AND c.principal_id=mnemion.principal()
      FOR SHARE OF g,s,c,k,p;
END
$$;

ALTER TABLE mnemion.capture_sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY capture_source_read ON mnemion.capture_sources FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_connector(connector_id)));
CREATE POLICY capture_source_admin ON mnemion.capture_sources FOR ALL TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.administrator())
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.administrator());
ALTER TABLE mnemion.capture_grants ENABLE ROW LEVEL SECURITY;
CREATE POLICY capture_grant_read ON mnemion.capture_grants FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_capture_source(source_id)));
CREATE POLICY capture_grant_admin ON mnemion.capture_grants FOR ALL TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.administrator())
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.administrator());
ALTER TABLE mnemion.capture_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY capture_event_operator ON mnemion.capture_events TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.owns_capture_source(source_id))
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.owns_capture_source(source_id));
CREATE POLICY capture_event_review ON mnemion.capture_events FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,20));
ALTER TABLE mnemion.capture_pages ENABLE ROW LEVEL SECURITY;
CREATE POLICY capture_page_operator ON mnemion.capture_pages TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND EXISTS(SELECT FROM mnemion.capture_grants g
        WHERE g.tenant_id=capture_pages.tenant_id AND g.grant_id=capture_pages.grant_id
          AND mnemion.owns_capture_source(g.source_id)))
    WITH CHECK(tenant_id=mnemion.tenant() AND EXISTS(SELECT FROM mnemion.capture_grants g
        WHERE g.tenant_id=capture_pages.tenant_id AND g.grant_id=capture_pages.grant_id
          AND mnemion.owns_capture_source(g.source_id)));
ALTER TABLE mnemion.capture_denials ENABLE ROW LEVEL SECURITY;
CREATE POLICY capture_denial_read ON mnemion.capture_denials FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_capture_source(source_id)));
REVOKE ALL ON mnemion.capture_sources,mnemion.capture_grants,mnemion.capture_events,
    mnemion.capture_pages,mnemion.capture_denials FROM mnemion_app,mnemion_worker;
GRANT SELECT,INSERT,UPDATE ON mnemion.capture_sources,mnemion.capture_grants TO mnemion_app;
GRANT SELECT,INSERT ON mnemion.capture_events,mnemion.capture_pages TO mnemion_app;
GRANT SELECT ON mnemion.capture_denials TO mnemion_app;
REVOKE ALL ON FUNCTION mnemion.owns_capture_source(uuid),mnemion.capture_source_has_history(uuid),
    mnemion.refresh_capture_members(uuid,uuid),
    mnemion.capture_members_changed(),mnemion.capture_memory_forgotten(),
    mnemion.revoke_capture_grant(uuid,uuid),mnemion.lock_capture_authority(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.owns_capture_source(uuid) TO mnemion_app,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.capture_source_has_history(uuid) TO mnemion_app;
GRANT EXECUTE ON FUNCTION mnemion.revoke_capture_grant(uuid,uuid) TO mnemion_app;
GRANT EXECUTE ON FUNCTION mnemion.lock_capture_authority(uuid,uuid) TO mnemion_app;
