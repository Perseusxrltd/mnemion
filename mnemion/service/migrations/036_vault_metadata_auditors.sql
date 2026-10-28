-- A metadata auditor is one exact API key, never every key of a person/agent.
-- Revocations retain their revision so a stale grant cannot recreate access.
CREATE TABLE mnemion.vault_auditors (
    tenant_id uuid NOT NULL,
    key_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    enabled boolean NOT NULL,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,key_id),
    FOREIGN KEY (tenant_id,key_id) REFERENCES mnemion.api_keys(tenant_id,id)
);
ALTER TABLE mnemion.vault_auditors ENABLE ROW LEVEL SECURITY;
CREATE POLICY vault_auditor_admin ON mnemion.vault_auditors TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.administrator())
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator());
GRANT SELECT,INSERT,UPDATE ON mnemion.vault_auditors TO mnemion_app;

CREATE FUNCTION mnemion.vault_auditor() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=mnemion,pg_temp AS $$
    SELECT EXISTS (
        SELECT FROM mnemion.vault_auditors a
        JOIN mnemion.api_keys k ON k.tenant_id=a.tenant_id AND k.id=a.key_id
        JOIN mnemion.principals p ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
        WHERE a.tenant_id=mnemion.tenant() AND a.enabled
          AND a.key_id=nullif(current_setting('mnemion.vault_key_id',true),'')::uuid
          AND k.principal_id=mnemion.principal() AND p.disabled_at IS NULL
          AND k.revoked_at IS NULL
          AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())
          AND (a.expires_at IS NULL OR a.expires_at>clock_timestamp())
    )
$$;
REVOKE ALL ON FUNCTION mnemion.vault_auditor() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.vault_auditor() TO mnemion_app;

-- Value reads/writes still require the existing per-entry rights; the new
-- role only extends metadata visibility and audit history in the service.
ALTER POLICY vault_entry_read ON mnemion.vault_entries
    USING (tenant_id=mnemion.tenant() AND
      ((SELECT mnemion.administrator()) OR (SELECT mnemion.vault_auditor())
        OR mnemion.vault_rights(id)>0));
ALTER POLICY vault_audit_read ON mnemion.vault_audit_events
    USING (tenant_id=mnemion.tenant() AND
      ((SELECT mnemion.administrator()) OR (SELECT mnemion.vault_auditor())));
ALTER TABLE mnemion.vault_audit_events
    ADD COLUMN target_key_id uuid,
    DROP CONSTRAINT vault_audit_events_action_check,
    ADD CONSTRAINT vault_audit_events_action_check
      CHECK (action IN ('list','get','put','grant','delete','export','import','auditor')),
    ADD CONSTRAINT vault_audit_target_check CHECK (target_key_id IS NULL OR action='auditor');
