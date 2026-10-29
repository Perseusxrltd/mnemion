-- Background inference uses the worker login, which does not apply reader RLS.
-- A current root lease is not permission to embed a file this scan could not
-- re-read. Neighboring items and native memories stay eligible. The space-level
-- lease, pause, and capture checks in embedding_source_current stay as they are.
-- This function does not exempt the connector principal: repair may read the
-- row, but inference may not.
CREATE FUNCTION mnemion.embedding_revision_current(revision uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT NOT EXISTS (
        SELECT FROM mnemion.memory_revisions r
        JOIN mnemion.connector_items i
          ON i.tenant_id=r.tenant_id AND i.space_id=r.space_id AND i.memory_id=r.memory_id
        WHERE r.tenant_id=mnemion.tenant() AND r.id=revision
          AND i.withheld_at IS NOT NULL AND i.state<>'deleted'
    )
$$;
REVOKE ALL ON FUNCTION mnemion.embedding_revision_current(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.embedding_revision_current(uuid) TO mnemion_app, mnemion_worker;
