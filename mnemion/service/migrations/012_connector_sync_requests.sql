-- One bounded control record per source. Requests arriving during a scan remain
-- pending until a subsequent complete scan acknowledges their generation.
CREATE TABLE mnemion.connector_sync_control (
    tenant_id uuid NOT NULL,
    connector_id uuid NOT NULL,
    requested_generation bigint NOT NULL DEFAULT 0 CHECK(requested_generation BETWEEN 0 AND 9007199254740991),
    completed_generation bigint NOT NULL DEFAULT 0 CHECK(completed_generation BETWEEN 0 AND requested_generation),
    requested_at timestamptz,
    completed_at timestamptz,
    last_attempt_at timestamptz,
    last_successful boolean,
    last_duration_seconds double precision,
    last_changed bigint NOT NULL DEFAULT 0,
    last_removed bigint NOT NULL DEFAULT 0,
    last_unchanged bigint NOT NULL DEFAULT 0,
    last_error_code text,
    PRIMARY KEY(tenant_id,connector_id),
    FOREIGN KEY(tenant_id,connector_id) REFERENCES mnemion.connectors(tenant_id,id)
);
ALTER TABLE mnemion.connector_sync_control ENABLE ROW LEVEL SECURITY;
CREATE POLICY sync_control_scope ON mnemion.connector_sync_control TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_connector(connector_id)))
    WITH CHECK(tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.owns_connector(connector_id)));
GRANT SELECT,INSERT,UPDATE ON mnemion.connector_sync_control TO mnemion_app;
