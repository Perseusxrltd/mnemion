-- Completed partial inventories keep their diagnostics in the existing run
-- receipt. A later clean scan clears them without changing source identities.
CREATE INDEX connector_latest_inventory ON mnemion.connector_runs
    (tenant_id,space_id,finished_at DESC,id DESC) WHERE state='completed';

-- A reader must learn that its own source became unavailable, even though
-- the source's content and operator-only tables are correctly hidden by RLS.
-- Return only counts for existing explicit grants, never paths, ACLs or IDs.
CREATE FUNCTION mnemion.source_health(selected uuid[]) RETURNS TABLE
    (unavailable_scopes bigint, incomplete_scopes bigint, skipped_documents bigint)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    WITH scopes AS (
        SELECT s.*, c.disabled_at AS connector_disabled, p.disabled_at AS publisher_disabled,
               p.administrator AS publisher_administrator
        FROM mnemion.space_grants g
        JOIN mnemion.principals caller ON caller.tenant_id=g.tenant_id AND caller.id=g.principal_id
        JOIN mnemion.connector_scopes s ON s.tenant_id=g.tenant_id AND s.space_id=g.space_id
        JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
        JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
        WHERE g.tenant_id=mnemion.tenant() AND g.principal_id=mnemion.principal()
          AND caller.disabled_at IS NULL AND (selected IS NULL OR s.space_id=ANY(selected))
    ), reports AS (
        SELECT s.suspended_at IS NOT NULL OR s.access_valid_until<=now()
                 OR s.connector_disabled IS NOT NULL OR s.publisher_disabled IS NOT NULL
                 OR s.publisher_administrator AS unavailable,
               coalesce((latest.result->>'skipped_documents')::bigint,0) AS skipped
        FROM scopes s
        LEFT JOIN LATERAL (
            SELECT r.result FROM mnemion.connector_runs r
            WHERE r.tenant_id=s.tenant_id AND r.space_id=s.space_id AND r.state='completed'
            ORDER BY r.finished_at DESC,r.id DESC LIMIT 1
        ) latest ON true
    )
    SELECT count(*) FILTER(WHERE unavailable), count(*) FILTER(WHERE skipped>0),
           coalesce(sum(skipped),0)::bigint FROM reports
$$;
REVOKE ALL ON FUNCTION mnemion.source_health(uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.source_health(uuid[]) TO mnemion_app;
