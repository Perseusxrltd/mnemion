-- Filing is a separate explicit opt-in. Existing journal permissions,
-- destination fingerprints and publisher identities remain unchanged.
ALTER TABLE mnemion.writeback_settings
    ADD COLUMN fold_enabled boolean NOT NULL DEFAULT false,
    ADD COLUMN fold_after_hours integer NOT NULL DEFAULT 24 CHECK (fold_after_hours BETWEEN 24 AND 8760),
    ADD COLUMN fold_interval_seconds integer NOT NULL DEFAULT 3600 CHECK (fold_interval_seconds BETWEEN 60 AND 86400),
    ADD COLUMN next_fold_at timestamptz,
    ADD COLUMN last_fold_at timestamptz,
    ADD COLUMN last_fold_commit text,
    ADD COLUMN last_fold_error text,
    ADD COLUMN last_fold_notes integer NOT NULL DEFAULT 0,
    ADD COLUMN last_fold_archived_files integer NOT NULL DEFAULT 0,
    ADD COLUMN last_fold_pending_notes integer NOT NULL DEFAULT 0,
    ADD COLUMN last_fold_pending_files integer NOT NULL DEFAULT 0,
    ADD COLUMN last_fold_read_bytes bigint NOT NULL DEFAULT 0,
    ADD COLUMN last_fold_written_bytes bigint NOT NULL DEFAULT 0;

CREATE INDEX journal_fold_due ON mnemion.writeback_settings(fingerprint,next_fold_at)
    WHERE fold_enabled AND NOT paused;
CREATE INDEX journal_push_due ON mnemion.writeback_settings(fingerprint,next_push_at)
    WHERE NOT paused;

CREATE FUNCTION mnemion.claim_journal_fold(fingerprints text[]) RETURNS SETOF mnemion.writeback_settings
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=mnemion,pg_temp AS $$
DECLARE selected writeback_settings%ROWTYPE;
BEGIN
    SELECT s.* INTO selected FROM writeback_settings s
      JOIN principals p ON p.tenant_id=s.tenant_id AND p.id=s.publisher_id
      JOIN api_keys k ON k.tenant_id=s.tenant_id AND k.id=s.key_id AND k.principal_id=p.id
      JOIN space_grants g ON g.tenant_id=s.tenant_id AND g.space_id=s.space_id AND g.principal_id=p.id
      WHERE s.fingerprint=ANY(fingerprints) AND NOT s.paused AND s.fold_enabled
        AND s.next_fold_at<=clock_timestamp()
        AND p.disabled_at IS NULL AND k.revoked_at IS NULL
        AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())
        AND g.role IN ('reviewer','administrator')
        AND NOT EXISTS (SELECT FROM writeback_events e WHERE e.tenant_id=s.tenant_id
                        AND e.space_id=s.space_id AND e.state IN ('pending','local'))
      ORDER BY s.next_fold_at,s.tenant_id,s.space_id FOR UPDATE OF s SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;
    UPDATE writeback_settings SET next_fold_at=clock_timestamp()+make_interval(secs=>fold_interval_seconds)
      WHERE tenant_id=selected.tenant_id AND space_id=selected.space_id;
    RETURN NEXT selected;
END $$;
REVOKE ALL ON FUNCTION mnemion.claim_journal_fold(text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.claim_journal_fold(text[]) TO mnemion_app;
