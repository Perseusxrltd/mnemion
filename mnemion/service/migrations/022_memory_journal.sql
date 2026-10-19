-- Publication is an explicit space policy. Credentials remain with the host's
-- Git credential manager; queued events refer to existing canonical revisions.
CREATE TABLE mnemion.writeback_settings (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    destination_id text NOT NULL,
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[a-f0-9]{64}$'),
    version integer NOT NULL DEFAULT 1 CHECK (version>0),
    publisher_id uuid NOT NULL,
    key_id uuid NOT NULL,
    paused boolean NOT NULL DEFAULT false,
    interval_seconds integer NOT NULL DEFAULT 300 CHECK (interval_seconds BETWEEN 30 AND 86400),
    next_push_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_push_at timestamptz,
    last_commit text,
    last_error text,
    last_entries integer NOT NULL DEFAULT 0,
    last_bytes bigint NOT NULL DEFAULT 0,
    created_by uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(tenant_id,space_id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id),
    FOREIGN KEY(tenant_id,publisher_id) REFERENCES mnemion.principals(tenant_id,id),
    FOREIGN KEY(tenant_id,key_id) REFERENCES mnemion.api_keys(tenant_id,id),
    FOREIGN KEY(tenant_id,created_by) REFERENCES mnemion.principals(tenant_id,id)
);
ALTER TABLE mnemion.writeback_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY writeback_settings_read ON mnemion.writeback_settings FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id));
CREATE POLICY writeback_settings_admin ON mnemion.writeback_settings FOR ALL TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.administrator() AND mnemion.authorized(space_id,40))
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator() AND mnemion.authorized(space_id,40));
CREATE POLICY writeback_settings_publisher ON mnemion.writeback_settings FOR UPDATE TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND publisher_id=mnemion.principal() AND mnemion.authorized(space_id,30))
    WITH CHECK (tenant_id=mnemion.tenant() AND publisher_id=mnemion.principal() AND mnemion.authorized(space_id,30));
GRANT SELECT,INSERT,UPDATE ON mnemion.writeback_settings TO mnemion_app;

CREATE FUNCTION mnemion.writeback_publisher_live(target uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=mnemion,pg_temp AS $$
    SELECT mnemion.authorized(target) AND EXISTS (
      SELECT FROM writeback_settings s JOIN principals p ON p.tenant_id=s.tenant_id AND p.id=s.publisher_id
      JOIN api_keys k ON k.tenant_id=s.tenant_id AND k.id=s.key_id AND k.principal_id=p.id
      JOIN space_grants g ON g.tenant_id=s.tenant_id AND g.space_id=s.space_id AND g.principal_id=p.id
      WHERE s.tenant_id=mnemion.tenant() AND s.space_id=target AND p.disabled_at IS NULL
        AND k.revoked_at IS NULL AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())
        AND g.role IN ('reviewer','administrator'))
$$;
REVOKE ALL ON FUNCTION mnemion.writeback_publisher_live(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.writeback_publisher_live(uuid) TO mnemion_app;

CREATE TABLE mnemion.writeback_events (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    memory_id uuid NOT NULL,
    revision_id uuid,
    version integer NOT NULL CHECK (version>0),
    writer uuid NOT NULL,
    action text NOT NULL CHECK (action IN ('upsert','forget','quarantine')),
    important boolean NOT NULL DEFAULT false,
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','local','pushed','suppressed')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    journaled_at timestamptz,
    pushed_at timestamptz,
    commit_id text,
    PRIMARY KEY(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.writeback_settings(tenant_id,space_id),
    FOREIGN KEY(tenant_id,space_id,memory_id) REFERENCES mnemion.memories(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,space_id,revision_id) REFERENCES mnemion.memory_revisions(tenant_id,space_id,id)
        ON DELETE SET NULL (revision_id),
    FOREIGN KEY(tenant_id,writer) REFERENCES mnemion.principals(tenant_id,id)
);
CREATE INDEX writeback_pending ON mnemion.writeback_events(tenant_id,space_id,created_at,id)
    WHERE state IN ('pending','local');
CREATE INDEX writeback_memory ON mnemion.writeback_events(tenant_id,space_id,memory_id);
ALTER TABLE mnemion.writeback_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY writeback_event_read ON mnemion.writeback_events FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id)
      AND (writer=mnemion.principal() OR mnemion.authorized(space_id,30)));
CREATE POLICY writeback_event_write ON mnemion.writeback_events FOR ALL TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,20)
      AND (writer=mnemion.principal() OR mnemion.authorized(space_id,30)))
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,20)
      AND (writer=mnemion.principal() OR mnemion.authorized(space_id,30)));
GRANT SELECT,INSERT,UPDATE ON mnemion.writeback_events TO mnemion_app;
GRANT SELECT,UPDATE ON mnemion.writeback_events TO mnemion_worker;
CREATE POLICY writeback_event_worker ON mnemion.writeback_events TO mnemion_worker
    USING (tenant_id=mnemion.tenant()) WITH CHECK (tenant_id=mnemion.tenant());

-- Only fixed schedule/identity data leaves this function. Content is fetched
-- later under the dedicated publisher's current key and explicit space grant.
CREATE FUNCTION mnemion.claim_writeback(fingerprints text[]) RETURNS SETOF mnemion.writeback_settings
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=mnemion,pg_temp AS $$
DECLARE selected writeback_settings%ROWTYPE;
BEGIN
    SELECT s.* INTO selected FROM writeback_settings s
      JOIN principals p ON p.tenant_id=s.tenant_id AND p.id=s.publisher_id
      JOIN api_keys k ON k.tenant_id=s.tenant_id AND k.id=s.key_id AND k.principal_id=p.id
      JOIN space_grants g ON g.tenant_id=s.tenant_id AND g.space_id=s.space_id AND g.principal_id=p.id
      WHERE s.fingerprint=ANY(fingerprints) AND NOT s.paused AND s.next_push_at<=clock_timestamp()
        AND p.disabled_at IS NULL AND k.revoked_at IS NULL
        AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())
        AND g.role IN ('reviewer','administrator')
        AND EXISTS (SELECT FROM writeback_events e WHERE e.tenant_id=s.tenant_id
                    AND e.space_id=s.space_id AND e.state IN ('pending','local'))
      ORDER BY s.next_push_at,s.tenant_id,s.space_id FOR UPDATE OF s SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;
    UPDATE writeback_settings SET next_push_at=clock_timestamp()+make_interval(secs=>interval_seconds)
      WHERE tenant_id=selected.tenant_id AND space_id=selected.space_id;
    RETURN NEXT selected;
END $$;
REVOKE ALL ON FUNCTION mnemion.claim_writeback(text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.claim_writeback(text[]) TO mnemion_app;
