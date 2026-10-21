-- A device keeps the selection it was actually authorized to capture. Changing
-- the default for future grants must never reinterpret its pending evidence.
ALTER TABLE mnemion.capture_sources ADD COLUMN policy_version integer NOT NULL DEFAULT 1
    CHECK(policy_version>=1);
CREATE TABLE mnemion.capture_policy_versions (
    tenant_id uuid NOT NULL,
    source_id uuid NOT NULL,
    policy_version integer NOT NULL CHECK(policy_version>=1),
    capture_mode text NOT NULL CHECK(capture_mode IN ('messages','complete')),
    capture_policy jsonb CHECK(capture_policy IS NULL OR jsonb_typeof(capture_policy)='object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    transition_id uuid,
    request_hash text CHECK(request_hash IS NULL OR request_hash ~ '^[a-f0-9]{64}$'),
    previous_grants text CHECK(previous_grants IN ('retain','revoke')),
    affected_grants integer CHECK(affected_grants>=0),
    PRIMARY KEY(tenant_id,source_id,policy_version),
    UNIQUE(tenant_id,transition_id),
    FOREIGN KEY(tenant_id,source_id) REFERENCES mnemion.capture_sources(tenant_id,source_id),
    CHECK((transition_id IS NULL AND request_hash IS NULL AND previous_grants IS NULL AND affected_grants IS NULL)
       OR (transition_id IS NOT NULL AND request_hash IS NOT NULL AND previous_grants IS NOT NULL AND affected_grants IS NOT NULL))
);
INSERT INTO mnemion.capture_policy_versions(tenant_id,source_id,policy_version,capture_mode,capture_policy,created_at)
    SELECT tenant_id,source_id,1,capture_mode,capture_policy,created_at FROM mnemion.capture_sources;
ALTER TABLE mnemion.capture_sources ADD CONSTRAINT capture_source_policy_version
    FOREIGN KEY(tenant_id,source_id,policy_version)
    REFERENCES mnemion.capture_policy_versions(tenant_id,source_id,policy_version)
    DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE mnemion.capture_grants ADD COLUMN policy_version integer NOT NULL DEFAULT 1
    CHECK(policy_version>=1);
ALTER TABLE mnemion.capture_grants ADD CONSTRAINT capture_grant_policy_version
    FOREIGN KEY(tenant_id,source_id,policy_version)
    REFERENCES mnemion.capture_policy_versions(tenant_id,source_id,policy_version);
CREATE INDEX capture_grants_source_policy ON mnemion.capture_grants(tenant_id,source_id,policy_version,grant_id);

ALTER TABLE mnemion.capture_policy_versions ENABLE ROW LEVEL SECURITY;
CREATE POLICY capture_policy_read ON mnemion.capture_policy_versions FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_capture_source(source_id)));
CREATE POLICY capture_policy_insert ON mnemion.capture_policy_versions FOR INSERT TO mnemion_app
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.administrator());
REVOKE ALL ON mnemion.capture_policy_versions FROM mnemion_app,mnemion_worker;
GRANT SELECT,INSERT ON mnemion.capture_policy_versions TO mnemion_app;

-- Revocation can hide the row through RLS. Its exact authenticated device may
-- learn only that its own authorization is inactive, without reading source
-- metadata after revocation or mistaking it for a temporary transport outage.
CREATE FUNCTION mnemion.capture_grant_refused(grant_value uuid, key_value uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.capture_grants g
      JOIN mnemion.capture_sources s USING(tenant_id,source_id)
      JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
      JOIN mnemion.api_keys k ON k.tenant_id=g.tenant_id AND k.id=g.device_key_id
      JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
      WHERE g.tenant_id=mnemion.tenant() AND g.grant_id=grant_value AND g.device_key_id=key_value
        AND k.principal_id=mnemion.principal() AND c.principal_id=mnemion.principal()
        AND (g.revoked_at IS NOT NULL OR s.revoked_at IS NOT NULL OR c.disabled_at IS NOT NULL
          OR k.revoked_at IS NOT NULL OR k.expires_at<=clock_timestamp()
          OR p.disabled_at IS NOT NULL OR p.administrator))
$$;
REVOKE ALL ON FUNCTION mnemion.capture_grant_refused(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.capture_grant_refused(uuid,uuid) TO mnemion_app;
