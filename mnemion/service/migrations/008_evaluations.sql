-- Test queries and labels are never part of memory/source retrieval tables.
CREATE TABLE mnemion.evaluation_datasets (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    name text NOT NULL CHECK(length(name) BETWEEN 1 AND 200),
    description text NOT NULL DEFAULT '',
    version integer NOT NULL CHECK(version>0),
    content_hash text NOT NULL,
    cases jsonb NOT NULL CHECK(jsonb_typeof(cases)='array' AND jsonb_array_length(cases)<=1000),
    state text NOT NULL DEFAULT 'active' CHECK(state IN ('active','invalidated','deleted')),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,space_id,id),
    UNIQUE(tenant_id,space_id,name,version),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id),
    FOREIGN KEY(tenant_id,created_by) REFERENCES mnemion.principals(tenant_id,id)
);
CREATE TABLE mnemion.evaluation_dependencies (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    PRIMARY KEY(tenant_id,space_id,dataset_id,memory_id,revision_id),
    FOREIGN KEY(tenant_id,space_id,dataset_id) REFERENCES mnemion.evaluation_datasets(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,space_id,memory_id) REFERENCES mnemion.memories(tenant_id,space_id,id)
);
CREATE INDEX evaluation_dependency_memory ON mnemion.evaluation_dependencies(tenant_id,space_id,memory_id);
CREATE TABLE mnemion.evaluation_runs (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    created_by uuid NOT NULL,
    key_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    generation_id text NOT NULL REFERENCES mnemion.embedding_generations(id),
    configuration jsonb NOT NULL,
    manifest jsonb NOT NULL,
    summary jsonb,
    state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','completed','failed','cancelled','invalidated')),
    progress integer NOT NULL DEFAULT 0 CHECK(progress>=0),
    total integer NOT NULL CHECK(total>0 AND total<=3000),
    lease_id uuid,
    lease_until timestamptz,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    PRIMARY KEY(tenant_id,space_id,id),
    UNIQUE(tenant_id,space_id,created_by,idempotency_key),
    FOREIGN KEY(tenant_id,space_id,dataset_id) REFERENCES mnemion.evaluation_datasets(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,created_by) REFERENCES mnemion.principals(tenant_id,id),
    FOREIGN KEY(tenant_id,key_id) REFERENCES mnemion.api_keys(tenant_id,id)
);
CREATE INDEX evaluation_run_ready ON mnemion.evaluation_runs(created_at,id)
    WHERE state IN ('queued','running');
CREATE UNIQUE INDEX evaluation_one_per_space ON mnemion.evaluation_runs(tenant_id,space_id)
    WHERE state IN ('queued','running');
CREATE TABLE mnemion.evaluation_results (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    run_id uuid NOT NULL,
    position integer NOT NULL CHECK(position>=0 AND position<3000),
    case_id text NOT NULL,
    mode text NOT NULL CHECK(mode IN ('lexical','semantic','hybrid')),
    result jsonb NOT NULL,
    human_assessment jsonb,
    assessed_by uuid,
    assessed_at timestamptz,
    assessment_version integer NOT NULL DEFAULT 0 CHECK(assessment_version>=0),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,space_id,run_id,position),
    FOREIGN KEY(tenant_id,space_id,run_id) REFERENCES mnemion.evaluation_runs(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,assessed_by) REFERENCES mnemion.principals(tenant_id,id)
);

DO $policies$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['evaluation_datasets','evaluation_dependencies','evaluation_runs','evaluation_results'] LOOP
        EXECUTE format('ALTER TABLE mnemion.%I ENABLE ROW LEVEL SECURITY',tab);
        EXECUTE format('CREATE POLICY evaluation_scope ON mnemion.%I TO mnemion_app
          USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30))
          WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30))',tab);
        EXECUTE format('CREATE POLICY evaluation_purge ON mnemion.%I TO mnemion_worker
          USING (tenant_id=mnemion.tenant()) WITH CHECK (tenant_id=mnemion.tenant())',tab);
    END LOOP;
END
$policies$;
REVOKE ALL ON mnemion.evaluation_datasets,mnemion.evaluation_dependencies,
    mnemion.evaluation_runs,mnemion.evaluation_results FROM mnemion_app,mnemion_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON mnemion.evaluation_datasets,mnemion.evaluation_dependencies,
    mnemion.evaluation_runs,mnemion.evaluation_results TO mnemion_app;
GRANT SELECT,UPDATE,DELETE ON mnemion.evaluation_datasets,mnemion.evaluation_dependencies,
    mnemion.evaluation_runs,mnemion.evaluation_results TO mnemion_worker;

-- One live evaluation per database deployment, across all API instances. Only
-- IDs, configuration and numeric metadata are returned; credentials stay hashed.
CREATE FUNCTION mnemion.claim_evaluation(lease uuid, generation text)
    RETURNS SETOF mnemion.evaluation_runs
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NOT pg_try_advisory_xact_lock(731293284010) THEN RETURN; END IF;
    IF EXISTS(SELECT FROM mnemion.evaluation_runs WHERE state='running' AND lease_until>now()) THEN RETURN; END IF;
    RETURN QUERY UPDATE mnemion.evaluation_runs SET state='running',lease_id=lease,
      lease_until=now()+interval '120 seconds',started_at=coalesce(started_at,now())
      WHERE (tenant_id,space_id,id)=(
        SELECT r.tenant_id,r.space_id,r.id FROM mnemion.evaluation_runs r
          JOIN mnemion.evaluation_datasets d ON d.tenant_id=r.tenant_id AND d.space_id=r.space_id AND d.id=r.dataset_id
          WHERE r.generation_id=generation AND d.state='active'
            AND (r.state='queued' OR (r.state='running' AND r.lease_until<=now()))
          ORDER BY r.created_at,r.id FOR UPDATE OF r SKIP LOCKED LIMIT 1)
      RETURNING *;
END
$$;
-- A revoked principal must not keep a queue slot forever. The caller can only
-- fail the exact lease it claimed, without reading or updating source content.
CREATE FUNCTION mnemion.fail_evaluation(run uuid, lease uuid, reason text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF reason NOT IN ('access_revoked','reference_unavailable','evaluation_error','time_budget_exhausted','generation_changed','corpus_limit','inference_busy','model_not_ready','evidence_validation_failed')
    THEN RAISE invalid_parameter_value; END IF;
    UPDATE mnemion.evaluation_runs SET state='failed',error_code=reason,
      lease_id=NULL,lease_until=NULL,finished_at=now()
      WHERE id=run AND state='running' AND lease_id=lease AND lease_until>now();
END
$$;
REVOKE ALL ON FUNCTION mnemion.claim_evaluation(uuid,text),mnemion.fail_evaluation(uuid,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.claim_evaluation(uuid,text),mnemion.fail_evaluation(uuid,uuid,text) TO mnemion_app;
