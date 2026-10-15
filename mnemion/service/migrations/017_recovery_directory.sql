-- Administrative recovery references are separate from searchable memories.
-- Recording a host or contact never creates host authority or a memory grant.
CREATE TABLE mnemion.recovery_directories (
    tenant_id uuid PRIMARY KEY REFERENCES mnemion.tenants(id),
    revision integer NOT NULL CHECK (revision > 0),
    document jsonb NOT NULL CHECK (
        jsonb_typeof(document) = 'object' AND octet_length(document::text) <= 16384
    ),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_by uuid NOT NULL,
    FOREIGN KEY (tenant_id, updated_by) REFERENCES mnemion.principals(tenant_id, id)
);
ALTER TABLE mnemion.recovery_directories ENABLE ROW LEVEL SECURITY;
CREATE POLICY recovery_directory_admin ON mnemion.recovery_directories TO mnemion_app
    USING (tenant_id = mnemion.tenant() AND mnemion.administrator())
    WITH CHECK (tenant_id = mnemion.tenant() AND mnemion.administrator());
GRANT SELECT, INSERT, UPDATE ON mnemion.recovery_directories TO mnemion_app;
