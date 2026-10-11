-- OAuth identities are pinned by an administrator, never by external role claims.
-- Each immutable binding owns a dedicated, non-exported credential. Existing
-- per-transaction API-key checks and recovery rotation therefore apply to OAuth.
ALTER TABLE mnemion.api_keys ADD CONSTRAINT key_identity
    UNIQUE (tenant_id, id, principal_id);
CREATE TABLE mnemion.oauth_bindings (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    key_id uuid NOT NULL UNIQUE,
    issuer text NOT NULL CHECK (length(issuer) BETWEEN 1 AND 2048 AND issuer !~ '[[:cntrl:]]'),
    subject text NOT NULL CHECK (length(subject) BETWEEN 1 AND 255 AND subject !~ '[[:cntrl:]]'),
    client_id text NOT NULL CHECK (length(client_id) BETWEEN 1 AND 2048 AND client_id !~ '[[:cntrl:]]'),
    identity_hash bytea NOT NULL UNIQUE CHECK (
        identity_hash=sha256(convert_to(issuer || E'\n' || subject || E'\n' || client_id, 'UTF8'))
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, key_id, principal_id)
        REFERENCES mnemion.api_keys(tenant_id, id, principal_id)
);
ALTER TABLE mnemion.oauth_bindings ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON mnemion.oauth_bindings TO mnemion_app;
REVOKE UPDATE, DELETE ON mnemion.oauth_bindings FROM mnemion_app, mnemion_worker;
CREATE POLICY oauth_read ON mnemion.oauth_bindings FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (principal_id=mnemion.principal() OR mnemion.administrator()));
CREATE POLICY oauth_create ON mnemion.oauth_bindings FOR INSERT TO mnemion_app
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator());

CREATE FUNCTION mnemion.authenticate_oauth(issuer_value text, subject_value text, client_value text)
    RETURNS TABLE(tenant_id uuid, principal_id uuid, key_id uuid)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT b.tenant_id, b.principal_id, b.key_id
    FROM mnemion.oauth_bindings b
    JOIN mnemion.api_keys k
      ON k.tenant_id=b.tenant_id AND k.id=b.key_id AND k.principal_id=b.principal_id
    JOIN mnemion.principals p ON p.tenant_id=b.tenant_id AND p.id=b.principal_id
    WHERE b.identity_hash=sha256(convert_to(issuer_value || E'\n' || subject_value || E'\n' || client_value, 'UTF8'))
      AND b.issuer=issuer_value AND b.subject=subject_value AND b.client_id=client_value
      AND k.revoked_at IS NULL AND p.disabled_at IS NULL
      AND (k.expires_at IS NULL OR k.expires_at > now())
$$;
REVOKE ALL ON FUNCTION mnemion.authenticate_oauth(text, text, text) FROM PUBLIC, mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.authenticate_oauth(text, text, text) TO mnemion_app;

CREATE FUNCTION mnemion.revoke_oauth(binding_id uuid)
    RETURNS TABLE(id uuid, revoked_at timestamptz)
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE mnemion.api_keys k SET revoked_at=coalesce(k.revoked_at, now())
    FROM mnemion.oauth_bindings b
    WHERE b.id=binding_id AND b.tenant_id=mnemion.tenant()
      AND (b.principal_id=mnemion.principal() OR mnemion.administrator())
      AND k.tenant_id=b.tenant_id AND k.id=b.key_id
    RETURNING b.id,k.revoked_at
$$;
REVOKE ALL ON FUNCTION mnemion.revoke_oauth(uuid) FROM PUBLIC, mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.revoke_oauth(uuid) TO mnemion_app;
