-- A large source inventory must not monopolize the shared indexing worker.
-- Dispatch metadata is independent of memory/model identity and survives restart.
-- A database sequence keeps turns fair across wall-clock corrections.
ALTER TABLE mnemion.tenants ADD COLUMN last_index_claim bigint;
ALTER TABLE mnemion.spaces ADD COLUMN last_index_claim bigint;
CREATE SEQUENCE mnemion.index_dispatch_turn AS bigint;
CREATE INDEX jobs_space_ready_idx
    ON mnemion.jobs(tenant_id,space_id,available_at,created_at,id)
    WHERE state IN ('pending','leased');

CREATE OR REPLACE FUNCTION mnemion.claim_job(lease uuid, seconds integer, generation text)
    RETURNS SETOF mnemion.jobs
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
    selected_tenant uuid;
    selected_space uuid;
    claimed mnemion.jobs;
    dispatch_turn bigint;
BEGIN
    -- Withdrawal is already visible at API acceptance. Physical purge must not
    -- wait behind an unrelated embedding backlog or a paused/unavailable model.
    UPDATE mnemion.jobs j SET state='leased',lease_id=lease,
        lease_until=now()+make_interval(secs=>greatest(5,least(seconds,3600))),
        attempts=j.attempts+1
    WHERE (j.tenant_id,j.space_id,j.id)=(
        SELECT q.tenant_id,q.space_id,q.id FROM mnemion.jobs q
        WHERE q.kind='purge'
          AND ((q.state='pending' AND q.available_at<=now())
            OR (q.state='leased' AND q.lease_until<now()))
        ORDER BY q.available_at,q.created_at,q.id
        FOR UPDATE OF q SKIP LOCKED LIMIT 1)
    RETURNING j.* INTO claimed;
    IF FOUND THEN
        RETURN NEXT claimed;
        RETURN;
    END IF;
    IF generation IS NULL THEN RETURN; END IF;

    -- Take a short dispatch turn for a tenant, then a space within that tenant.
    -- More source spaces cannot give one tenant all of the worker's turns.
    -- No model work or database transaction is held across inference.
    SELECT t.id INTO selected_tenant FROM mnemion.tenants t
    WHERE EXISTS (
        SELECT FROM mnemion.jobs j
        LEFT JOIN mnemion.space_embedding_settings s
          ON s.tenant_id=j.tenant_id AND s.space_id=j.space_id
        LEFT JOIN mnemion.reindex_runs r
          ON r.tenant_id=j.tenant_id AND r.space_id=j.space_id AND r.id=j.reindex_run_id
        WHERE j.tenant_id=t.id AND j.kind='embed' AND j.generation_id=generation
          AND ((j.state='pending' AND j.available_at<=now())
            OR (j.state='leased' AND j.lease_until<now()))
          AND ((j.reindex_run_id IS NULL AND NOT coalesce(s.inference_paused,false)
              AND (s.space_id IS NULL OR s.active_generation_id=generation))
            OR (s.candidate_run_id=r.id AND r.state='running')))
    ORDER BY t.last_index_claim NULLS FIRST,t.created_at,t.id
    FOR UPDATE OF t SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;

    SELECT space.id INTO selected_space FROM mnemion.spaces space
    WHERE space.tenant_id=selected_tenant AND EXISTS (
        SELECT FROM mnemion.jobs j
        LEFT JOIN mnemion.space_embedding_settings s
          ON s.tenant_id=j.tenant_id AND s.space_id=j.space_id
        LEFT JOIN mnemion.reindex_runs r
          ON r.tenant_id=j.tenant_id AND r.space_id=j.space_id AND r.id=j.reindex_run_id
        WHERE j.tenant_id=space.tenant_id AND j.space_id=space.id
          AND j.kind='embed' AND j.generation_id=generation
          AND ((j.state='pending' AND j.available_at<=now())
            OR (j.state='leased' AND j.lease_until<now()))
          AND ((j.reindex_run_id IS NULL AND NOT coalesce(s.inference_paused,false)
              AND (s.space_id IS NULL OR s.active_generation_id=generation))
            OR (s.candidate_run_id=r.id AND r.state='running')))
    ORDER BY space.last_index_claim NULLS FIRST,space.created_at,space.id
    FOR UPDATE OF space SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;

    UPDATE mnemion.jobs j SET state='leased',lease_id=lease,
        lease_until=now()+make_interval(secs=>greatest(5,least(seconds,3600))),
        attempts=j.attempts+1
    WHERE (j.tenant_id,j.space_id,j.id)=(
        SELECT q.tenant_id,q.space_id,q.id FROM mnemion.jobs q
        LEFT JOIN mnemion.space_embedding_settings s
          ON s.tenant_id=q.tenant_id AND s.space_id=q.space_id
        LEFT JOIN mnemion.reindex_runs r
          ON r.tenant_id=q.tenant_id AND r.space_id=q.space_id AND r.id=q.reindex_run_id
        WHERE q.tenant_id=selected_tenant AND q.space_id=selected_space
          AND q.kind='embed' AND q.generation_id=generation
          AND ((q.state='pending' AND q.available_at<=now())
            OR (q.state='leased' AND q.lease_until<now()))
          AND ((q.reindex_run_id IS NULL AND NOT coalesce(s.inference_paused,false)
              AND (s.space_id IS NULL OR s.active_generation_id=generation))
            OR (s.candidate_run_id=r.id AND r.state='running'))
        ORDER BY q.available_at,q.created_at,q.id
        FOR UPDATE OF q SKIP LOCKED LIMIT 1)
    RETURNING j.* INTO claimed;
    IF NOT FOUND THEN RETURN; END IF;

    dispatch_turn := nextval('mnemion.index_dispatch_turn'::regclass);
    UPDATE mnemion.tenants SET last_index_claim=dispatch_turn WHERE id=selected_tenant;
    UPDATE mnemion.spaces SET last_index_claim=dispatch_turn
      WHERE tenant_id=selected_tenant AND id=selected_space;
    RETURN NEXT claimed;
END
$$;
REVOKE ALL ON FUNCTION mnemion.claim_job(uuid,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.claim_job(uuid,integer,text) TO mnemion_worker;
