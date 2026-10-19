-- Source recovery identities are not principals, permissions or native history.
-- Quarantined origins can exist without recoverable content or a memory row.
CREATE TABLE mnemion.journal_recovery_origins (
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    space_id uuid NOT NULL,
    origin text NOT NULL,
    memory_id uuid NOT NULL,
    source_version bigint NOT NULL CHECK (source_version BETWEEN 1 AND 9007199254740991),
    source_digest text NOT NULL CHECK (source_digest ~ '^[a-f0-9]{64}$'),
    source_action text NOT NULL CHECK (source_action IN ('upsert','quarantine')),
    local_version integer CHECK (local_version >= 1),
    locally_modified boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,space_id,origin),
    UNIQUE (tenant_id,memory_id)
);
-- A newer recovery ledger can retain a hold for a space absent from an older
-- backup. Such a registry entry grants no access and creates no content.
ALTER TABLE mnemion.journal_recovery_origins ENABLE ROW LEVEL SECURITY;
GRANT SELECT,INSERT,UPDATE ON mnemion.journal_recovery_origins TO mnemion_app;
GRANT SELECT ON mnemion.journal_recovery_origins TO mnemion_worker;
CREATE POLICY journal_recovery_read ON mnemion.journal_recovery_origins FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,40) AND mnemion.administrator());
CREATE POLICY journal_recovery_insert ON mnemion.journal_recovery_origins FOR INSERT TO mnemion_app
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,40) AND mnemion.administrator());
CREATE POLICY journal_recovery_update ON mnemion.journal_recovery_origins FOR UPDATE TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,40) AND mnemion.administrator())
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,40) AND mnemion.administrator());
CREATE POLICY journal_recovery_worker ON mnemion.journal_recovery_origins FOR SELECT TO mnemion_worker
    USING (tenant_id=mnemion.tenant());

-- Check collisions without disclosing another private space's content or registry.
CREATE FUNCTION mnemion.recovery_identity_available(target_space uuid, candidate uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT mnemion.administrator() AND mnemion.authorized(target_space,40)
        AND NOT EXISTS (
            SELECT FROM mnemion.memories
            WHERE tenant_id=mnemion.tenant() AND id=candidate AND space_id<>target_space
        )
        AND NOT EXISTS (
            SELECT FROM mnemion.journal_recovery_origins
            WHERE tenant_id=mnemion.tenant() AND memory_id=candidate AND space_id<>target_space
        )
        AND NOT EXISTS (
            SELECT FROM mnemion.recovery_denials
            WHERE tenant_id=mnemion.tenant() AND memory_id=candidate AND space_id<>target_space
        )
$$;
REVOKE ALL ON FUNCTION mnemion.recovery_identity_available(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.recovery_identity_available(uuid,uuid) TO mnemion_app;
