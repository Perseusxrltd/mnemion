-- Credentials are separate from memory, source, indexing and worker tables.
-- The application encrypts values before SQL; the database never receives the
-- vault encryption key or a plaintext value.
CREATE TABLE mnemion.vault_entries (
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    id uuid NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    version integer NOT NULL CHECK (version > 0),
    access_version integer NOT NULL DEFAULT 1 CHECK (access_version > 0),
    key_id text NOT NULL CHECK (key_id ~ '^[a-f0-9]{32}$'),
    nonce bytea,
    ciphertext bytea,
    created_by uuid NOT NULL,
    updated_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    deleted_at timestamptz,
    PRIMARY KEY (tenant_id,id),
    FOREIGN KEY (tenant_id,created_by) REFERENCES mnemion.principals(tenant_id,id),
    FOREIGN KEY (tenant_id,updated_by) REFERENCES mnemion.principals(tenant_id,id),
    CHECK ((deleted_at IS NULL AND nonce IS NOT NULL AND ciphertext IS NOT NULL AND octet_length(nonce)=12
            AND octet_length(ciphertext) BETWEEN 17 AND 65552)
        OR (deleted_at IS NOT NULL AND nonce IS NULL AND ciphertext IS NULL))
);
CREATE UNIQUE INDEX vault_live_name ON mnemion.vault_entries(tenant_id,name)
    WHERE deleted_at IS NULL;

CREATE TABLE mnemion.vault_grants (
    tenant_id uuid NOT NULL,
    entry_id uuid NOT NULL,
    subject_kind text NOT NULL CHECK (subject_kind IN ('person','key')),
    subject_id uuid NOT NULL,
    permissions integer NOT NULL CHECK (permissions IN (1,3,5,7)),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,entry_id,subject_kind,subject_id),
    FOREIGN KEY (tenant_id,entry_id) REFERENCES mnemion.vault_entries(tenant_id,id)
);
-- Subject membership is checked by the application while holding the same
-- tenant lock as key/person retirement. Permissions never cross a tenant.
CREATE FUNCTION mnemion.vault_rights(entry uuid) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=mnemion,pg_temp AS $$
    SELECT coalesce(bit_or(g.permissions),0)::integer
    FROM mnemion.vault_grants g
    JOIN mnemion.vault_entries e ON e.tenant_id=g.tenant_id AND e.id=g.entry_id
    JOIN mnemion.api_keys k ON k.tenant_id=g.tenant_id
      AND k.id=nullif(current_setting('mnemion.vault_key_id',true),'')::uuid
      AND k.principal_id=mnemion.principal()
    JOIN mnemion.principals p ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
    WHERE g.tenant_id=mnemion.tenant() AND g.entry_id=entry AND e.deleted_at IS NULL
      AND p.disabled_at IS NULL AND k.revoked_at IS NULL
      AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())
      AND ((g.subject_kind='key' AND g.subject_id=k.id)
        OR (g.subject_kind='person' AND g.subject_id=p.id AND p.kind='human'
          AND EXISTS (SELECT FROM mnemion.sign_in_sessions s
            WHERE s.tenant_id=k.tenant_id AND s.key_id=k.id)))
$$;
REVOKE ALL ON FUNCTION mnemion.vault_rights(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.vault_rights(uuid) TO mnemion_app;

ALTER TABLE mnemion.vault_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY vault_entry_read ON mnemion.vault_entries FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant()
      AND (mnemion.administrator() OR mnemion.vault_rights(id)>0));
CREATE POLICY vault_entry_create ON mnemion.vault_entries FOR INSERT TO mnemion_app
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator());
CREATE POLICY vault_entry_update ON mnemion.vault_entries FOR UPDATE TO mnemion_app
    USING (tenant_id=mnemion.tenant()
      AND (mnemion.administrator() OR (mnemion.vault_rights(id)&4)=4))
    WITH CHECK (tenant_id=mnemion.tenant());
GRANT SELECT,INSERT,UPDATE ON mnemion.vault_entries TO mnemion_app;

ALTER TABLE mnemion.vault_grants ENABLE ROW LEVEL SECURITY;
CREATE POLICY vault_grant_admin ON mnemion.vault_grants TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.administrator())
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator());
GRANT SELECT,INSERT,UPDATE,DELETE ON mnemion.vault_grants TO mnemion_app;

CREATE TABLE mnemion.vault_denials (
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    entry_id uuid NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,entry_id)
);
ALTER TABLE mnemion.vault_denials ENABLE ROW LEVEL SECURITY;
CREATE POLICY vault_denial_admin ON mnemion.vault_denials TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.administrator())
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator());
GRANT SELECT,INSERT ON mnemion.vault_denials TO mnemion_app;

CREATE TABLE mnemion.vault_audit_events (
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    id uuid NOT NULL,
    principal_id uuid NOT NULL,
    key_id uuid NOT NULL,
    entry_id uuid,
    action text NOT NULL CHECK (action IN ('list','get','put','grant','delete','export','import')),
    outcome text NOT NULL CHECK (outcome IN ('allowed','denied','conflict','unavailable','invalid')),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,id),
    FOREIGN KEY (tenant_id,principal_id) REFERENCES mnemion.principals(tenant_id,id),
    FOREIGN KEY (tenant_id,key_id) REFERENCES mnemion.api_keys(tenant_id,id)
);
CREATE INDEX vault_audit_time ON mnemion.vault_audit_events(tenant_id,occurred_at DESC,id);
ALTER TABLE mnemion.vault_audit_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY vault_audit_read ON mnemion.vault_audit_events FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.administrator());
CREATE POLICY vault_audit_append ON mnemion.vault_audit_events FOR INSERT TO mnemion_app
    WITH CHECK (tenant_id=mnemion.tenant() AND principal_id=mnemion.principal()
      AND key_id=nullif(current_setting('mnemion.vault_key_id',true),'')::uuid);
GRANT SELECT,INSERT ON mnemion.vault_audit_events TO mnemion_app;
-- No vault table/function privilege is granted to the memory indexing worker.
