-- Optional, bounded language-model jobs. Generated text stays outside recall
-- until a reviewer explicitly applies a single-memory organization proposal.
CREATE TABLE mnemion.librarian_settings (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    version integer NOT NULL CHECK(version>0),
    profile_id text NOT NULL,
    profile_fingerprint text NOT NULL CHECK(length(profile_fingerprint)=64),
    enabled boolean NOT NULL DEFAULT false,
    network_egress_approved boolean NOT NULL DEFAULT false,
    mode text NOT NULL CHECK(mode IN ('organize','review')),
    max_memories integer NOT NULL CHECK(max_memories BETWEEN 1 AND 12),
    max_calls_per_day integer NOT NULL CHECK(max_calls_per_day BETWEEN 1 AND 1000),
    interval_minutes integer CHECK(interval_minutes BETWEEN 60 AND 10080),
    next_run_at timestamptz,
    created_by uuid NOT NULL,
    key_id uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,space_id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id),
    FOREIGN KEY(tenant_id,created_by) REFERENCES mnemion.principals(tenant_id,id),
    FOREIGN KEY(tenant_id,key_id) REFERENCES mnemion.api_keys(tenant_id,id)
);
CREATE INDEX librarian_schedule_ready ON mnemion.librarian_settings(next_run_at)
    WHERE enabled AND interval_minutes IS NOT NULL;
CREATE TABLE mnemion.librarian_runs (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    profile_id text NOT NULL,
    profile_fingerprint text NOT NULL,
    settings_version integer NOT NULL,
    mode text NOT NULL CHECK(mode IN ('organize','review')),
    configuration jsonb NOT NULL,
    state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','completed','failed','cancelled')),
    selected integer NOT NULL DEFAULT 0 CHECK(selected BETWEEN 0 AND 12),
    processed integer NOT NULL DEFAULT 0 CHECK(processed BETWEEN 0 AND 12),
    skipped integer NOT NULL DEFAULT 0 CHECK(skipped BETWEEN 0 AND 12),
    proposal_count integer NOT NULL DEFAULT 0 CHECK(proposal_count BETWEEN 0 AND 144),
    calls_reserved integer NOT NULL DEFAULT 0 CHECK(calls_reserved BETWEEN 0 AND 12),
    calls_completed integer NOT NULL DEFAULT 0 CHECK(calls_completed BETWEEN 0 AND 12),
    input_units bigint NOT NULL DEFAULT 0 CHECK(input_units>=0),
    output_tokens bigint CHECK(output_tokens>=0),
    request_bytes bigint NOT NULL DEFAULT 0 CHECK(request_bytes>=0),
    response_bytes bigint NOT NULL DEFAULT 0 CHECK(response_bytes>=0),
    latency_ms double precision NOT NULL DEFAULT 0 CHECK(latency_ms>=0),
    error_code text,
    created_by uuid NOT NULL,
    key_id uuid NOT NULL,
    lease_id uuid,
    lease_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    PRIMARY KEY(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id),
    FOREIGN KEY(tenant_id,created_by) REFERENCES mnemion.principals(tenant_id,id),
    FOREIGN KEY(tenant_id,key_id) REFERENCES mnemion.api_keys(tenant_id,id)
);
CREATE UNIQUE INDEX librarian_one_per_space ON mnemion.librarian_runs(tenant_id,space_id)
    WHERE state IN ('queued','running');
CREATE INDEX librarian_run_ready ON mnemion.librarian_runs(created_at,id)
    WHERE state='queued';
CREATE INDEX librarian_run_history ON mnemion.librarian_runs(tenant_id,space_id,created_at DESC,id DESC);
CREATE TABLE mnemion.librarian_items (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    run_id uuid NOT NULL,
    position integer NOT NULL CHECK(position BETWEEN 0 AND 11),
    memory_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    memory_version integer NOT NULL,
    state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','completed','skipped')),
    reason text,
    PRIMARY KEY(tenant_id,space_id,run_id,position),
    FOREIGN KEY(tenant_id,space_id,run_id) REFERENCES mnemion.librarian_runs(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,space_id,memory_id) REFERENCES mnemion.memories(tenant_id,space_id,id)
);
CREATE TABLE mnemion.librarian_proposals (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    suggestion jsonb,
    state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','accepted','rejected','undone','invalidated')),
    version integer NOT NULL DEFAULT 1 CHECK(version>0),
    previous_revision_id uuid,
    applied_revision_id uuid,
    applied_version integer,
    decided_by uuid,
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,space_id,run_id) REFERENCES mnemion.librarian_runs(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,space_id,memory_id) REFERENCES mnemion.memories(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,decided_by) REFERENCES mnemion.principals(tenant_id,id)
);
CREATE INDEX librarian_proposal_history ON mnemion.librarian_proposals(tenant_id,space_id,created_at DESC,id DESC);
CREATE INDEX librarian_proposal_pending ON mnemion.librarian_proposals(tenant_id,space_id) WHERE state='pending';
CREATE TABLE mnemion.librarian_dependencies (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    memory_version integer NOT NULL,
    PRIMARY KEY(tenant_id,space_id,proposal_id,memory_id),
    FOREIGN KEY(tenant_id,space_id,proposal_id) REFERENCES mnemion.librarian_proposals(tenant_id,space_id,id),
    FOREIGN KEY(tenant_id,space_id,memory_id) REFERENCES mnemion.memories(tenant_id,space_id,id)
);
CREATE INDEX librarian_dependency_memory ON mnemion.librarian_dependencies(tenant_id,space_id,memory_id);
CREATE TABLE mnemion.librarian_observations (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    profile_fingerprint text NOT NULL,
    mode text NOT NULL,
    memory_version integer NOT NULL,
    outcome text NOT NULL CHECK(outcome IN ('attempted','completed','skipped')),
    checked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,space_id,memory_id,profile_fingerprint,mode),
    FOREIGN KEY(tenant_id,space_id,memory_id) REFERENCES mnemion.memories(tenant_id,space_id,id)
);
CREATE TABLE mnemion.librarian_budgets (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    day date NOT NULL,
    calls_reserved integer NOT NULL DEFAULT 0 CHECK(calls_reserved>=0),
    PRIMARY KEY(tenant_id,space_id,day),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id)
);
ALTER TABLE mnemion.librarian_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY librarian_settings_read ON mnemion.librarian_settings FOR SELECT TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30));
CREATE POLICY librarian_settings_write ON mnemion.librarian_settings TO mnemion_app
    USING(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,40))
    WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,40));
GRANT SELECT,INSERT,UPDATE ON mnemion.librarian_settings TO mnemion_app;
DO $policies$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['librarian_runs','librarian_items','librarian_proposals','librarian_dependencies','librarian_observations','librarian_budgets'] LOOP
        EXECUTE format('ALTER TABLE mnemion.%I ENABLE ROW LEVEL SECURITY',tab);
        EXECUTE format('CREATE POLICY librarian_scope ON mnemion.%I TO mnemion_app
            USING(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30))
            WITH CHECK(tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30))',tab);
        EXECUTE format('CREATE POLICY librarian_purge ON mnemion.%I TO mnemion_worker
            USING(tenant_id=mnemion.tenant()) WITH CHECK(tenant_id=mnemion.tenant())',tab);
        EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON mnemion.%I TO mnemion_app',tab);
        EXECUTE format('GRANT SELECT,UPDATE,DELETE ON mnemion.%I TO mnemion_worker',tab);
    END LOOP;
END
$policies$;
-- One live librarian job per deployment. An interrupted call is never retried
-- automatically: its provider might already have charged for it.
CREATE FUNCTION mnemion.claim_librarian(lease uuid, fingerprints text[])
    RETURNS SETOF mnemion.librarian_runs
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NOT pg_try_advisory_xact_lock(731293284020) THEN RETURN; END IF;
    UPDATE mnemion.librarian_runs SET state='failed',error_code='interrupted',
        finished_at=now(),lease_id=NULL,lease_until=NULL
        WHERE state='running' AND lease_until<=now();
    -- A cancelled caller may still be unwinding an HTTP request. Its lease
    -- continues to occupy the slot until that caller releases it or it expires.
    IF EXISTS(SELECT FROM mnemion.librarian_runs WHERE lease_until>now()) THEN RETURN; END IF;
    RETURN QUERY UPDATE mnemion.librarian_runs SET state='running',lease_id=lease,
        lease_until=now()+interval '120 seconds',started_at=now()
        WHERE (tenant_id,space_id,id)=(
            SELECT r.tenant_id,r.space_id,r.id FROM mnemion.librarian_runs r
            WHERE r.state='queued' AND r.profile_fingerprint=ANY(fingerprints)
            ORDER BY r.created_at,r.id FOR UPDATE SKIP LOCKED LIMIT 1)
        RETURNING *;
END
$$;
CREATE FUNCTION mnemion.claim_librarian_schedule(fingerprints text[])
    RETURNS SETOF mnemion.librarian_settings
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    RETURN QUERY UPDATE mnemion.librarian_settings SET
        next_run_at=now()+interval '1 minute'*interval_minutes
        WHERE (tenant_id,space_id)=(
            SELECT s.tenant_id,s.space_id FROM mnemion.librarian_settings s
            WHERE s.enabled AND s.interval_minutes IS NOT NULL AND s.next_run_at<=now()
                AND s.profile_fingerprint=ANY(fingerprints)
            ORDER BY s.next_run_at,s.space_id FOR UPDATE SKIP LOCKED LIMIT 1)
        RETURNING *;
END
$$;
CREATE FUNCTION mnemion.fail_librarian(run uuid, lease uuid, reason text,
    sent bigint DEFAULT 0, received bigint DEFAULT 0, elapsed double precision DEFAULT 0) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF reason NOT IN ('access_revoked','reference_unavailable','provider_error','time_budget_exhausted',
        'librarian_profile_unavailable','configuration_changed','daily_budget_exhausted',
        'input_budget_exceeded','inference_busy','tokenizer_unavailable','credentials_unavailable','librarian_error','run_cancelled')
        OR sent<0 OR sent>1048576 OR received<0 OR received>2097152 OR elapsed<0 OR elapsed>600000
    THEN RAISE invalid_parameter_value; END IF;
    UPDATE mnemion.librarian_runs SET state=CASE WHEN state='cancelled' THEN state ELSE 'failed' END,
        error_code=CASE WHEN state='cancelled' THEN error_code ELSE reason END,
        request_bytes=request_bytes+sent,response_bytes=response_bytes+received,latency_ms=latency_ms+elapsed,
        lease_id=NULL,lease_until=NULL,finished_at=now()
        WHERE id=run AND state IN ('running','cancelled') AND lease_id=lease AND lease_until>now();
END
$$;
REVOKE ALL ON FUNCTION mnemion.claim_librarian(uuid,text[]),mnemion.claim_librarian_schedule(text[]),
    mnemion.fail_librarian(uuid,uuid,text,bigint,bigint,double precision) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.claim_librarian(uuid,text[]),mnemion.claim_librarian_schedule(text[]),
    mnemion.fail_librarian(uuid,uuid,text,bigint,bigint,double precision) TO mnemion_app;
