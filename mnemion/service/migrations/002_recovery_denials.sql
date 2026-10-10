-- Negative identity records survive restoration of an older positive snapshot.
-- A space or memory may have been created after that snapshot, so these IDs
-- deliberately have no foreign key to the restored space/memory tables.
CREATE TABLE mnemion.recovery_denials (
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    space_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, memory_id)
);
INSERT INTO mnemion.recovery_denials (tenant_id, space_id, memory_id, requested_at)
    SELECT tenant_id, space_id, memory_id, requested_at FROM mnemion.deletion_receipts;
ALTER TABLE mnemion.recovery_denials ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON mnemion.recovery_denials TO mnemion_app;
GRANT SELECT ON mnemion.recovery_denials TO mnemion_worker;
REVOKE UPDATE, DELETE ON mnemion.recovery_denials FROM mnemion_app, mnemion_worker;
CREATE POLICY denial_read ON mnemion.recovery_denials FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id));
CREATE POLICY denial_append ON mnemion.recovery_denials FOR INSERT TO mnemion_app
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id, 20));
CREATE POLICY denial_worker ON mnemion.recovery_denials FOR SELECT TO mnemion_worker
    USING (tenant_id=mnemion.tenant());
