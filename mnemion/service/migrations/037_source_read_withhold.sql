-- A read that stops the inventory withholds every non-deleted item this run
-- did not genuinely re-read. validated_run is set only by a content observation.
-- A body-free retain, a new run id, and a lease refresh do not clear withheld_at.
-- Both columns stay NULL on existing rows. There is no backfill.
-- read_scope keeps the 035 authorized_spaces(10) check and adds the withhold.
-- The connector principal can still re-read and repair. Capture, vault, worker,
-- and the other read_scope tables are unchanged.
ALTER TABLE mnemion.connector_items ADD COLUMN withheld_at timestamptz;
ALTER TABLE mnemion.connector_items ADD COLUMN validated_run uuid;
CREATE INDEX connector_items_withheld_idx ON mnemion.connector_items(tenant_id, memory_id)
    WHERE withheld_at IS NOT NULL;

CREATE FUNCTION mnemion.source_memory_withheld(memory uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS (
        SELECT FROM mnemion.connector_items i
        JOIN mnemion.connector_scopes s ON s.tenant_id=i.tenant_id AND s.space_id=i.space_id
        JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
        WHERE i.tenant_id=mnemion.tenant() AND i.memory_id=memory AND i.withheld_at IS NOT NULL
          AND c.principal_id IS DISTINCT FROM mnemion.principal()
    )
$$;
REVOKE ALL ON FUNCTION mnemion.source_memory_withheld(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.source_memory_withheld(uuid) TO mnemion_app;

ALTER POLICY read_scope ON mnemion.memories
    USING (tenant_id=mnemion.tenant()
           AND space_id IN (SELECT mnemion.authorized_spaces(10))
           AND NOT mnemion.source_memory_withheld(id));
ALTER POLICY read_scope ON mnemion.memory_revisions
    USING (tenant_id=mnemion.tenant()
           AND space_id IN (SELECT mnemion.authorized_spaces(10))
           AND NOT mnemion.source_memory_withheld(memory_id));
