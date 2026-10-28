-- Resolve the caller's current grants once per statement, rather than running
-- the complete source/capture authorization check for every candidate row.
-- This is not a connection or application permission cache: the existing
-- authorized() function still checks every grant at the statement's snapshot.
CREATE FUNCTION mnemion.authorized_spaces(level integer DEFAULT 10)
    RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT g.space_id FROM mnemion.space_grants g
    WHERE g.tenant_id=mnemion.tenant() AND g.principal_id=mnemion.principal()
      AND mnemion.authorized(g.space_id,level)
$$;
REVOKE ALL ON FUNCTION mnemion.authorized_spaces(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.authorized_spaces(integer) TO mnemion_app, mnemion_worker;

-- An uncorrelated subquery is evaluated once for each policy in a statement.
-- Keep both SELECT and ALL policies: ALL also participates in reads, while its
-- USING and WITH CHECK clauses must continue to require contributor access.
DO $policies$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY[
        'sources', 'source_revisions', 'memories', 'memory_revisions', 'embeddings',
        'operations', 'jobs', 'idempotency_keys', 'core_blocks', 'core_block_revisions',
        'legacy_aliases', 'deletion_receipts'
    ] LOOP
        EXECUTE format(
            'ALTER POLICY read_scope ON mnemion.%I USING (tenant_id=mnemion.tenant() AND space_id IN (SELECT mnemion.authorized_spaces(10)))',
            tab);
        EXECUTE format(
            'ALTER POLICY write_scope ON mnemion.%I USING (tenant_id=mnemion.tenant() AND space_id IN (SELECT mnemion.authorized_spaces(20))) WITH CHECK (tenant_id=mnemion.tenant() AND space_id IN (SELECT mnemion.authorized_spaces(20)))',
            tab);
    END LOOP;
END
$policies$;

ALTER POLICY audit_read ON mnemion.audit_events
    USING (tenant_id=mnemion.tenant() AND (
        (space_id IS NULL AND mnemion.administrator()) OR
        (space_id IS NOT NULL AND space_id IN (SELECT mnemion.authorized_spaces(30)))));
ALTER POLICY change_note_read ON mnemion.memory_change_notes
    USING (tenant_id=mnemion.tenant()
      AND space_id IN (SELECT mnemion.authorized_spaces(30)) AND EXISTS (
        SELECT FROM mnemion.memories m WHERE m.tenant_id=memory_change_notes.tenant_id
          AND m.space_id=memory_change_notes.space_id AND m.id=memory_change_notes.memory_id
          AND m.deleted_at IS NULL));
