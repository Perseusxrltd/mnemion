-- Expiry is an explicit organization policy. Historical approvals without an
-- expiry rule remain indefinite; no issuer or deadline is invented for them.
ALTER TABLE mnemion.capture_policy_versions ADD COLUMN approved_by uuid;
ALTER TABLE mnemion.capture_events ADD COLUMN policy_version integer;
ALTER TABLE mnemion.capture_events ADD CONSTRAINT capture_event_policy_version
    FOREIGN KEY(tenant_id,source_id,policy_version)
    REFERENCES mnemion.capture_policy_versions(tenant_id,source_id,policy_version);

CREATE TABLE mnemion.capture_expiries (
    tenant_id uuid NOT NULL,
    source_id uuid NOT NULL,
    lineage_id text NOT NULL CHECK(lineage_id ~ '^[a-f0-9]{64}$'),
    policy_version integer NOT NULL,
    first_accepted_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL CHECK(expires_at>first_accepted_at),
    state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','leased','expired')),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_id uuid,
    lease_until timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
    error_code text CHECK(length(error_code)<=100),
    completed_at timestamptz,
    PRIMARY KEY(tenant_id,source_id,lineage_id),
    FOREIGN KEY(tenant_id,source_id,policy_version)
        REFERENCES mnemion.capture_policy_versions(tenant_id,source_id,policy_version),
    CHECK((state='leased' AND lease_id IS NOT NULL AND lease_until IS NOT NULL)
       OR (state<>'leased' AND lease_id IS NULL AND lease_until IS NULL)),
    CHECK((state='expired')=(completed_at IS NOT NULL))
);
CREATE INDEX capture_expiry_due ON mnemion.capture_expiries(expires_at,available_at)
    WHERE state<>'expired';

-- The application supplies an already accepted family and approved policy,
-- never a client clock or deadline. Revisions, retries and new device grants
-- cannot extend a family's earliest approved deadline.
CREATE FUNCTION mnemion.schedule_capture_expiry(source uuid, lineage text, version_value integer)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE policy mnemion.capture_policy_versions; age integer; first_seen timestamptz;
BEGIN
    IF NOT mnemion.owns_capture_source(source) THEN
        RAISE EXCEPTION 'Capture expiry requires the source operator';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('capture:'||source::text,0));
    SELECT * INTO policy FROM mnemion.capture_policy_versions
      WHERE tenant_id=mnemion.tenant() AND source_id=source AND policy_version=version_value;
    IF NOT FOUND OR policy.capture_policy->>'retention' IS DISTINCT FROM 'expire_after' THEN RETURN; END IF;
    IF policy.approved_by IS NULL OR policy.capture_policy->>'format'<>'mnemion-capture-policy-v3'
       OR policy.capture_policy->>'expiry_scope'<>'captured_fragment_family' THEN
        RAISE EXCEPTION 'Capture expiry lacks an approved policy';
    END IF;
    age:=(policy.capture_policy->>'retention_days')::integer;
    IF age IS NULL OR age<1 OR age>3650 THEN RAISE EXCEPTION 'Invalid capture expiry period'; END IF;
    SELECT min(accepted_at) INTO first_seen FROM mnemion.capture_events
      WHERE tenant_id=mnemion.tenant() AND source_id=source AND lineage_id=lineage
        AND policy_version=version_value AND memory_id IS NOT NULL;
    IF first_seen IS NULL THEN RETURN; END IF;
    INSERT INTO mnemion.capture_expiries(tenant_id,source_id,lineage_id,policy_version,first_accepted_at,expires_at)
      VALUES(mnemion.tenant(),source,lineage,version_value,first_seen,first_seen+age*interval '24 hours')
      ON CONFLICT(tenant_id,source_id,lineage_id) DO UPDATE
        SET policy_version=excluded.policy_version,first_accepted_at=excluded.first_accepted_at,
            expires_at=excluded.expires_at
        WHERE capture_expiries.state<>'expired' AND excluded.expires_at<capture_expiries.expires_at;
END
$$;

CREATE FUNCTION mnemion.claim_capture_expiry(lease uuid, seconds integer)
    RETURNS SETOF mnemion.capture_expiries
    LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE mnemion.capture_expiries SET state='leased',lease_id=lease,
      lease_until=clock_timestamp()+make_interval(secs=>greatest(5,least(seconds,300))),
      attempts=least(attempts,1000000)+1
      WHERE (tenant_id,source_id,lineage_id)=(
        SELECT tenant_id,source_id,lineage_id FROM mnemion.capture_expiries
          WHERE expires_at<=clock_timestamp() AND available_at<=clock_timestamp()
            AND (state='pending' OR (state='leased' AND lease_until<clock_timestamp()))
          ORDER BY expires_at,source_id,lineage_id FOR UPDATE SKIP LOCKED LIMIT 1)
      RETURNING *
$$;

-- These grants permit canonical deletion receipts only for a due capture lease.
-- They give the worker no application identity or arbitrary retention policy.
CREATE FUNCTION mnemion.capture_expiry_authorized(memory uuid, actor uuid DEFAULT NULL)
    RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.capture_events e
      JOIN mnemion.capture_expiries x USING(tenant_id,source_id,lineage_id)
      JOIN mnemion.capture_policy_versions p ON p.tenant_id=x.tenant_id
        AND p.source_id=x.source_id AND p.policy_version=x.policy_version
      JOIN mnemion.memories m ON m.tenant_id=e.tenant_id AND m.space_id=e.space_id AND m.id=e.memory_id
      WHERE e.tenant_id=mnemion.tenant() AND e.memory_id=memory
        AND (actor IS NULL OR m.created_by=actor) AND p.approved_by IS NOT NULL
        AND p.capture_policy->>'retention'='expire_after'
        AND x.expires_at<=clock_timestamp() AND x.state='leased' AND x.lease_until>clock_timestamp())
$$;
-- Administrators can observe cleanup without receiving access to captured
-- bodies or another source's deletion receipts.
CREATE FUNCTION mnemion.capture_purges_pending(source uuid)
    RETURNS bigint LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NOT (mnemion.administrator() OR mnemion.owns_capture_source(source)) THEN
        RAISE EXCEPTION 'Capture cleanup observations require source authority';
    END IF;
    RETURN (SELECT count(*) FROM mnemion.capture_events e JOIN mnemion.deletion_receipts d
      ON d.tenant_id=e.tenant_id AND d.space_id=e.space_id AND d.memory_id=e.memory_id
      WHERE e.tenant_id=mnemion.tenant() AND e.source_id=source AND d.purged_at IS NULL);
END
$$;
ALTER TABLE mnemion.capture_expiries ENABLE ROW LEVEL SECURITY;
CREATE POLICY capture_expiry_read ON mnemion.capture_expiries FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_capture_source(source_id)));
CREATE POLICY capture_expiry_worker ON mnemion.capture_expiries TO mnemion_worker
    USING(tenant_id=mnemion.tenant()) WITH CHECK(tenant_id=mnemion.tenant());
REVOKE ALL ON mnemion.capture_expiries FROM mnemion_app,mnemion_worker;
GRANT SELECT ON mnemion.capture_expiries TO mnemion_app,mnemion_worker;
GRANT UPDATE(state,available_at,lease_id,lease_until,attempts,error_code,completed_at)
    ON mnemion.capture_expiries TO mnemion_worker;
CREATE POLICY capture_event_worker_read ON mnemion.capture_events FOR SELECT TO mnemion_worker
    USING(tenant_id=mnemion.tenant());
CREATE POLICY capture_source_worker_read ON mnemion.capture_sources FOR SELECT TO mnemion_worker
    USING(tenant_id=mnemion.tenant());
CREATE POLICY capture_policy_worker_read ON mnemion.capture_policy_versions FOR SELECT TO mnemion_worker
    USING(tenant_id=mnemion.tenant());
GRANT SELECT ON mnemion.capture_events,mnemion.capture_sources,mnemion.capture_policy_versions TO mnemion_worker;
CREATE POLICY fence_worker_read ON mnemion.space_fences FOR SELECT TO mnemion_worker
    USING(tenant_id=mnemion.tenant());
GRANT SELECT ON mnemion.space_fences TO mnemion_worker;
CREATE POLICY capture_denial_expiry ON mnemion.capture_denials FOR INSERT TO mnemion_worker
    WITH CHECK(tenant_id=mnemion.tenant() AND EXISTS(
      SELECT FROM mnemion.capture_expiries x WHERE x.tenant_id=capture_denials.tenant_id
        AND x.source_id=capture_denials.source_id AND x.lineage_id=capture_denials.lineage_id
        AND x.state='leased' AND x.lease_until>clock_timestamp() AND x.expires_at<=clock_timestamp()));
CREATE POLICY capture_denial_worker_read ON mnemion.capture_denials FOR SELECT TO mnemion_worker
    USING(tenant_id=mnemion.tenant());
GRANT SELECT,INSERT ON mnemion.capture_denials TO mnemion_worker;
CREATE POLICY recovery_denial_expiry ON mnemion.recovery_denials FOR INSERT TO mnemion_worker
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.capture_expiry_authorized(memory_id));
GRANT INSERT ON mnemion.recovery_denials TO mnemion_worker;
CREATE POLICY audit_capture_expiry ON mnemion.audit_events FOR INSERT TO mnemion_worker
    WITH CHECK(tenant_id=mnemion.tenant() AND action='memory.deleted'
      AND details->>'cause'='capture_retention' AND CASE
        WHEN resource_id ~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
        THEN mnemion.capture_expiry_authorized(resource_id::uuid,principal_id) ELSE false END);
REVOKE ALL ON FUNCTION mnemion.schedule_capture_expiry(uuid,text,integer),
    mnemion.claim_capture_expiry(uuid,integer),mnemion.capture_expiry_authorized(uuid,uuid),
    mnemion.capture_purges_pending(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.schedule_capture_expiry(uuid,text,integer),
    mnemion.capture_purges_pending(uuid) TO mnemion_app;
GRANT EXECUTE ON FUNCTION mnemion.claim_capture_expiry(uuid,integer),
    mnemion.capture_expiry_authorized(uuid,uuid) TO mnemion_worker;
