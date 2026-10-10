-- Each space retains an active index while its candidate builds independently.
CREATE TABLE mnemion.reindex_runs (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    generation_id text NOT NULL REFERENCES mnemion.embedding_generations(id),
    previous_generation_id text NOT NULL REFERENCES mnemion.embedding_generations(id),
    state text NOT NULL DEFAULT 'running' CHECK(state IN ('running','paused','cancelled','activated')),
    cursor_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    scan_complete boolean NOT NULL DEFAULT false,
    lease_id uuid,
    lease_until timestamptz,
    network_egress_approved boolean NOT NULL DEFAULT false,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id),
    FOREIGN KEY(tenant_id,created_by) REFERENCES mnemion.principals(tenant_id,id)
);
CREATE UNIQUE INDEX reindex_one_candidate ON mnemion.reindex_runs(tenant_id,space_id)
    WHERE state IN ('running','paused');
CREATE INDEX reindex_backfill_ready ON mnemion.reindex_runs(updated_at,id)
    WHERE state='running' AND NOT scan_complete;

CREATE TABLE mnemion.space_embedding_settings (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    active_generation_id text NOT NULL REFERENCES mnemion.embedding_generations(id),
    previous_generation_id text REFERENCES mnemion.embedding_generations(id),
    candidate_run_id uuid,
    inference_paused boolean NOT NULL DEFAULT false,
    version integer NOT NULL DEFAULT 1 CHECK(version>0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,space_id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id),
    FOREIGN KEY(tenant_id,space_id,candidate_run_id) REFERENCES mnemion.reindex_runs(tenant_id,space_id,id)
);
ALTER TABLE mnemion.jobs ADD COLUMN reindex_run_id uuid;
ALTER TABLE mnemion.jobs ADD FOREIGN KEY(tenant_id,space_id,reindex_run_id)
    REFERENCES mnemion.reindex_runs(tenant_id,space_id,id);
CREATE UNIQUE INDEX reindex_revision_job ON mnemion.jobs(tenant_id,space_id,reindex_run_id,revision_id)
    WHERE reindex_run_id IS NOT NULL;

DO $policies$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['space_embedding_settings','reindex_runs'] LOOP
        EXECUTE format('ALTER TABLE mnemion.%I ENABLE ROW LEVEL SECURITY',tab);
        EXECUTE format('CREATE POLICY model_read ON mnemion.%I FOR SELECT TO mnemion_app
            USING(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id))',tab);
        EXECUTE format('CREATE POLICY model_admin ON mnemion.%I FOR ALL TO mnemion_app
            USING(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,40))
            WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,40))',tab);
        EXECUTE format('CREATE POLICY model_worker ON mnemion.%I TO mnemion_worker
            USING(tenant_id=mnemion.tenant()) WITH CHECK(tenant_id=mnemion.tenant())',tab);
    END LOOP;
END
$policies$;
GRANT SELECT,INSERT,UPDATE ON mnemion.space_embedding_settings,mnemion.reindex_runs TO mnemion_app;
GRANT SELECT ON mnemion.space_embedding_settings TO mnemion_worker;
GRANT SELECT,UPDATE ON mnemion.reindex_runs TO mnemion_worker;

-- Workers can check freshness without receiving connector membership records.
CREATE FUNCTION mnemion.embedding_source_current(space uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS(SELECT FROM mnemion.spaces WHERE tenant_id=mnemion.tenant() AND id=space)
      AND NOT EXISTS(SELECT FROM mnemion.connector_scopes s
        JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
        JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
        WHERE s.tenant_id=mnemion.tenant() AND s.space_id=space
          AND (s.operator_paused OR s.suspended_at IS NOT NULL OR s.access_valid_until<=now()
               OR c.disabled_at IS NOT NULL OR p.disabled_at IS NOT NULL OR p.administrator))
$$;
REVOKE ALL ON FUNCTION mnemion.embedding_source_current(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.embedding_source_current(uuid) TO mnemion_app,mnemion_worker;

-- Claims carry IDs only. Text is read later inside the worker's tenant scope.
CREATE FUNCTION mnemion.claim_reindex(lease uuid, generations text[])
    RETURNS SETOF mnemion.reindex_runs
    LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE mnemion.reindex_runs SET lease_id=lease,lease_until=now()+interval '30 seconds'
    WHERE (tenant_id,space_id,id)=(
        SELECT tenant_id,space_id,id FROM mnemion.reindex_runs
        WHERE state='running' AND NOT scan_complete AND generation_id=ANY(generations)
          AND (lease_until IS NULL OR lease_until<now())
        ORDER BY updated_at,id FOR UPDATE SKIP LOCKED LIMIT 1)
    RETURNING *
$$;
REVOKE ALL ON FUNCTION mnemion.claim_reindex(uuid,text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.claim_reindex(uuid,text[]) TO mnemion_worker;

CREATE OR REPLACE FUNCTION mnemion.claim_job(lease uuid, seconds integer, generation text)
    RETURNS SETOF mnemion.jobs
    LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE mnemion.jobs SET state='leased',lease_id=lease,
        lease_until=now()+make_interval(secs=>greatest(5,least(seconds,3600))),attempts=attempts+1
    WHERE (tenant_id,space_id,id)=(
        SELECT j.tenant_id,j.space_id,j.id FROM mnemion.jobs j
        LEFT JOIN mnemion.space_embedding_settings s ON s.tenant_id=j.tenant_id AND s.space_id=j.space_id
        LEFT JOIN mnemion.reindex_runs r ON r.tenant_id=j.tenant_id AND r.space_id=j.space_id AND r.id=j.reindex_run_id
        WHERE ((j.state='pending' AND j.available_at<=now()) OR (j.state='leased' AND j.lease_until<now()))
          AND (j.kind='purge' OR (j.generation_id=generation AND (
            (j.reindex_run_id IS NULL AND NOT coalesce(s.inference_paused,false)
              AND (s.space_id IS NULL OR s.active_generation_id=generation))
            OR (s.candidate_run_id=r.id AND r.state='running'))))
        ORDER BY j.available_at,j.created_at,j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1)
    RETURNING *
$$;
