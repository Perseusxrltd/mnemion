-- Backfill is a separate, explicitly approved job. Enabling a journal never
-- exports older memories. Its cursor and captured events commit together.
CREATE TABLE mnemion.writeback_backfills (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    policy_version integer NOT NULL CHECK (policy_version>0),
    requested_by uuid NOT NULL,
    state text NOT NULL CHECK (state IN ('running','paused','blocked','completed','cancelled')),
    cutoff_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    cursor_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    total_at_start bigint NOT NULL CHECK (total_at_start>=0),
    examined bigint NOT NULL DEFAULT 0 CHECK (examined>=0),
    queued bigint NOT NULL DEFAULT 0 CHECK (queued>=0),
    already_journaled bigint NOT NULL DEFAULT 0 CHECK (already_journaled>=0),
    excluded bigint NOT NULL DEFAULT 0 CHECK (excluded>=0),
    rejected bigint NOT NULL DEFAULT 0 CHECK (rejected>=0),
    content_bytes bigint NOT NULL DEFAULT 0 CHECK (content_bytes>=0),
    errors jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(errors)='array' AND jsonb_array_length(errors)<=50),
    last_error text,
    next_batch_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    PRIMARY KEY(tenant_id,space_id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.writeback_settings(tenant_id,space_id),
    FOREIGN KEY(tenant_id,requested_by) REFERENCES mnemion.principals(tenant_id,id)
);
CREATE INDEX journal_backfill_due ON mnemion.writeback_backfills(next_batch_at)
    WHERE state='running';
CREATE INDEX writeback_current_version ON mnemion.writeback_events(tenant_id,space_id,memory_id,version)
    WHERE action='upsert';
ALTER TABLE mnemion.writeback_backfills ENABLE ROW LEVEL SECURITY;
CREATE POLICY writeback_backfill_admin ON mnemion.writeback_backfills FOR ALL TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.administrator() AND mnemion.authorized(space_id,40))
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator() AND mnemion.authorized(space_id,40));
CREATE POLICY writeback_backfill_publisher_read ON mnemion.writeback_backfills FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30) AND EXISTS (
      SELECT FROM mnemion.writeback_settings s WHERE s.tenant_id=writeback_backfills.tenant_id
        AND s.space_id=writeback_backfills.space_id AND s.publisher_id=mnemion.principal()));
CREATE POLICY writeback_backfill_publisher_update ON mnemion.writeback_backfills FOR UPDATE TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30) AND EXISTS (
      SELECT FROM mnemion.writeback_settings s WHERE s.tenant_id=writeback_backfills.tenant_id
        AND s.space_id=writeback_backfills.space_id AND s.publisher_id=mnemion.principal()))
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30) AND EXISTS (
      SELECT FROM mnemion.writeback_settings s WHERE s.tenant_id=writeback_backfills.tenant_id
        AND s.space_id=writeback_backfills.space_id AND s.publisher_id=mnemion.principal()));
GRANT SELECT,INSERT,UPDATE ON mnemion.writeback_backfills TO mnemion_app;

-- A scoped publisher cannot read other principals or their grants. Expose only
-- the current approval's validity, without granting identity-table visibility.
CREATE FUNCTION mnemion.writeback_backfill_approval_live(target uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=mnemion,pg_temp AS $$
    SELECT mnemion.authorized(target,30) AND EXISTS (
      SELECT FROM writeback_backfills b JOIN writeback_settings s
        ON s.tenant_id=b.tenant_id AND s.space_id=b.space_id
      JOIN principals p ON p.tenant_id=b.tenant_id AND p.id=b.requested_by
      JOIN space_grants g ON g.tenant_id=b.tenant_id AND g.space_id=b.space_id AND g.principal_id=p.id
      WHERE b.tenant_id=mnemion.tenant() AND b.space_id=target
        AND (s.publisher_id=mnemion.principal() OR (mnemion.administrator() AND mnemion.authorized(target,40)))
        AND p.disabled_at IS NULL AND p.administrator AND g.role='administrator')
$$;
REVOKE ALL ON FUNCTION mnemion.writeback_backfill_approval_live(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.writeback_backfill_approval_live(uuid) TO mnemion_app;

-- The scheduler exposes only already-approved publisher/settings identities.
-- Capturing content happens later under current publisher and space authority.
CREATE FUNCTION mnemion.claim_journal_backfill(fingerprints text[]) RETURNS SETOF mnemion.writeback_settings
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=mnemion,pg_temp AS $$
DECLARE selected writeback_settings%ROWTYPE;
BEGIN
    SELECT s.* INTO selected FROM writeback_settings s
      JOIN writeback_backfills b ON b.tenant_id=s.tenant_id AND b.space_id=s.space_id
      JOIN principals p ON p.tenant_id=s.tenant_id AND p.id=s.publisher_id
      JOIN api_keys k ON k.tenant_id=s.tenant_id AND k.id=s.key_id AND k.principal_id=p.id
      JOIN space_grants g ON g.tenant_id=s.tenant_id AND g.space_id=s.space_id AND g.principal_id=p.id
      JOIN principals a ON a.tenant_id=b.tenant_id AND a.id=b.requested_by
      JOIN space_grants ag ON ag.tenant_id=b.tenant_id AND ag.space_id=b.space_id AND ag.principal_id=a.id
      WHERE s.fingerprint=ANY(fingerprints) AND NOT s.paused
        AND b.state='running' AND b.policy_version=s.version AND b.next_batch_at<=clock_timestamp()
        AND p.disabled_at IS NULL AND k.revoked_at IS NULL
        AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())
        AND g.role IN ('reviewer','administrator')
        AND a.disabled_at IS NULL AND a.administrator AND ag.role='administrator'
        AND NOT EXISTS (SELECT FROM writeback_events e WHERE e.tenant_id=s.tenant_id
                        AND e.space_id=s.space_id AND e.state IN ('pending','local'))
      ORDER BY b.next_batch_at,b.tenant_id,b.space_id FOR UPDATE OF b SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;
    UPDATE writeback_backfills SET next_batch_at=clock_timestamp()+interval '30 seconds'
      WHERE tenant_id=selected.tenant_id AND space_id=selected.space_id;
    RETURN NEXT selected;
END $$;
REVOKE ALL ON FUNCTION mnemion.claim_journal_backfill(text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.claim_journal_backfill(text[]) TO mnemion_app;
