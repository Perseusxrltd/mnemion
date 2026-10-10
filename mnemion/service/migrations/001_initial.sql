CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS mnemion;

DO $roles$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mnemion_app') THEN
        CREATE ROLE mnemion_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mnemion_worker') THEN
        CREATE ROLE mnemion_worker NOLOGIN;
    END IF;
END
$roles$;

CREATE TABLE mnemion.tenants (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE mnemion.principals (
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    id uuid NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    kind text NOT NULL CHECK (kind IN ('human', 'application')),
    administrator boolean NOT NULL DEFAULT false,
    disabled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);
CREATE TABLE mnemion.api_keys (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    principal_id uuid NOT NULL,
    name text NOT NULL,
    token_hash text NOT NULL UNIQUE,
    prefix text NOT NULL,
    expires_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, principal_id) REFERENCES mnemion.principals(tenant_id, id)
);
CREATE TABLE mnemion.spaces (
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    id uuid NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    description text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);
CREATE TABLE mnemion.space_grants (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    role text NOT NULL CHECK (role IN ('reader', 'contributor', 'reviewer', 'administrator')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id, principal_id),
    FOREIGN KEY (tenant_id, space_id) REFERENCES mnemion.spaces(tenant_id, id),
    FOREIGN KEY (tenant_id, principal_id) REFERENCES mnemion.principals(tenant_id, id)
);

CREATE TABLE mnemion.sources (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    title text NOT NULL,
    uri text,
    created_by uuid NOT NULL,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, space_id) REFERENCES mnemion.spaces(tenant_id, id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES mnemion.principals(tenant_id, id)
);
CREATE TABLE mnemion.source_revisions (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    source_id uuid NOT NULL,
    content text NOT NULL,
    content_hash text NOT NULL,
    media_type text NOT NULL DEFAULT 'text/plain',
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, space_id, source_id) REFERENCES mnemion.sources(tenant_id, space_id, id)
);
CREATE TABLE mnemion.memories (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    subject text,
    kind text NOT NULL DEFAULT 'fact' CHECK (kind IN ('fact', 'event', 'preference', 'procedure', 'note')),
    current_revision_id uuid,
    version integer NOT NULL DEFAULT 0 CHECK (version >= 0),
    review_state text NOT NULL DEFAULT 'ordinary' CHECK (review_state IN ('ordinary', 'quarantined')),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    PRIMARY KEY (tenant_id, space_id, id),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, space_id) REFERENCES mnemion.spaces(tenant_id, id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES mnemion.principals(tenant_id, id)
);
CREATE TABLE mnemion.memory_revisions (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    memory_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    subject text,
    kind text NOT NULL CHECK (kind IN ('fact', 'event', 'preference', 'procedure', 'note')),
    content text NOT NULL CHECK (length(content) > 0),
    content_hash text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
    source_revision_id uuid NOT NULL,
    source_start integer NOT NULL DEFAULT 0,
    source_end integer NOT NULL,
    claim_status text NOT NULL DEFAULT 'observed' CHECK (claim_status IN ('observed', 'verified', 'contested', 'superseded', 'retracted')),
    valid_from timestamptz,
    valid_to timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    search_text tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    PRIMARY KEY (tenant_id, space_id, id),
    UNIQUE (tenant_id, space_id, memory_id, version),
    UNIQUE (tenant_id, space_id, memory_id, id),
    FOREIGN KEY (tenant_id, space_id, memory_id) REFERENCES mnemion.memories(tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, space_id, source_revision_id) REFERENCES mnemion.source_revisions(tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES mnemion.principals(tenant_id, id),
    CHECK (source_start >= 0 AND source_end >= source_start),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);
ALTER TABLE mnemion.memories ADD CONSTRAINT memory_current_revision
    FOREIGN KEY (tenant_id, space_id, id, current_revision_id)
    REFERENCES mnemion.memory_revisions(tenant_id, space_id, memory_id, id) DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX memory_revision_text_idx ON mnemion.memory_revisions USING gin(search_text);
CREATE INDEX memory_space_updated_idx ON mnemion.memories(tenant_id, space_id, updated_at, id);

CREATE TABLE mnemion.embedding_generations (
    id text PRIMARY KEY,
    model text NOT NULL,
    configuration jsonb NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions > 0 AND dimensions <= 4096),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE mnemion.embeddings (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    generation_id text NOT NULL REFERENCES mnemion.embedding_generations(id),
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    start_offset integer NOT NULL CHECK (start_offset >= 0),
    end_offset integer NOT NULL CHECK (end_offset > start_offset),
    embedding vector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id, revision_id, generation_id, chunk_index),
    FOREIGN KEY (tenant_id, space_id, revision_id) REFERENCES mnemion.memory_revisions(tenant_id, space_id, id)
);
CREATE TABLE mnemion.operations (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    memory_id uuid,
    revision_id uuid,
    kind text NOT NULL CHECK (kind IN ('ingest', 'revise', 'delete', 'reindex')),
    state text NOT NULL DEFAULT 'accepted' CHECK (state IN ('accepted', 'indexing', 'ready', 'failed', 'cancelled')),
    error_code text,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id, id),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, space_id) REFERENCES mnemion.spaces(tenant_id, id),
    FOREIGN KEY (tenant_id, space_id, memory_id) REFERENCES mnemion.memories(tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES mnemion.principals(tenant_id, id)
);
CREATE TABLE mnemion.jobs (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    operation_id uuid NOT NULL,
    revision_id uuid,
    generation_id text REFERENCES mnemion.embedding_generations(id),
    kind text NOT NULL CHECK (kind IN ('embed', 'purge')),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'leased', 'ready', 'failed', 'cancelled')),
    attempts integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_id uuid,
    lease_until timestamptz,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, space_id, operation_id) REFERENCES mnemion.operations(tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, space_id, revision_id) REFERENCES mnemion.memory_revisions(tenant_id, space_id, id)
);
CREATE INDEX jobs_ready_idx ON mnemion.jobs(available_at, created_at) WHERE state IN ('pending', 'leased');
CREATE TABLE mnemion.idempotency_keys (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    key text NOT NULL,
    request_hash text NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id, principal_id, key),
    FOREIGN KEY (tenant_id, space_id) REFERENCES mnemion.spaces(tenant_id, id),
    FOREIGN KEY (tenant_id, principal_id) REFERENCES mnemion.principals(tenant_id, id)
);
CREATE TABLE mnemion.core_blocks (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    key text NOT NULL,
    version integer NOT NULL DEFAULT 1,
    content text NOT NULL,
    updated_by uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id, key),
    FOREIGN KEY (tenant_id, space_id) REFERENCES mnemion.spaces(tenant_id, id),
    FOREIGN KEY (tenant_id, updated_by) REFERENCES mnemion.principals(tenant_id, id)
);
CREATE TABLE mnemion.core_block_revisions (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    key text NOT NULL,
    version integer NOT NULL,
    content text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id, key, version),
    FOREIGN KEY (tenant_id, space_id, key) REFERENCES mnemion.core_blocks(tenant_id, space_id, key),
    FOREIGN KEY (tenant_id, created_by) REFERENCES mnemion.principals(tenant_id, id)
);
CREATE TABLE mnemion.deletion_receipts (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    purged_at timestamptz,
    PRIMARY KEY (tenant_id, space_id, memory_id),
    FOREIGN KEY (tenant_id, space_id, memory_id) REFERENCES mnemion.memories(tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, space_id, operation_id) REFERENCES mnemion.operations(tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, requested_by) REFERENCES mnemion.principals(tenant_id, id)
);
CREATE TABLE mnemion.audit_events (
    tenant_id uuid NOT NULL,
    space_id uuid,
    id uuid NOT NULL,
    principal_id uuid NOT NULL,
    action text NOT NULL,
    resource_id text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, principal_id) REFERENCES mnemion.principals(tenant_id, id),
    FOREIGN KEY (tenant_id, space_id) REFERENCES mnemion.spaces(tenant_id, id)
);
CREATE TABLE mnemion.legacy_aliases (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    legacy_id text NOT NULL,
    memory_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, space_id, legacy_id),
    FOREIGN KEY (tenant_id, space_id, memory_id) REFERENCES mnemion.memories(tenant_id, space_id, id)
);

CREATE FUNCTION mnemion.tenant() RETURNS uuid LANGUAGE sql STABLE AS
    $$ SELECT nullif(current_setting('mnemion.tenant_id', true), '')::uuid $$;
CREATE FUNCTION mnemion.principal() RETURNS uuid LANGUAGE sql STABLE AS
    $$ SELECT nullif(current_setting('mnemion.principal_id', true), '')::uuid $$;
CREATE FUNCTION mnemion.administrator() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS (
        SELECT FROM mnemion.principals
        WHERE tenant_id=mnemion.tenant() AND id=mnemion.principal()
          AND administrator AND disabled_at IS NULL
    )
$$;
CREATE FUNCTION mnemion.authorized(space uuid, level integer DEFAULT 10) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT EXISTS (
        SELECT FROM mnemion.space_grants g JOIN mnemion.principals p
          ON p.tenant_id=g.tenant_id AND p.id=g.principal_id
        WHERE g.tenant_id=mnemion.tenant() AND g.space_id=space
          AND g.principal_id=mnemion.principal() AND p.disabled_at IS NULL
          AND CASE g.role WHEN 'reader' THEN 10 WHEN 'contributor' THEN 20
              WHEN 'reviewer' THEN 30 WHEN 'administrator' THEN 40 END >= level
    )
$$;
CREATE FUNCTION mnemion.authenticate(token text)
    RETURNS TABLE(tenant_id uuid, principal_id uuid, key_id uuid, administrator boolean)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT k.tenant_id, k.principal_id, k.id, p.administrator
    FROM mnemion.api_keys k JOIN mnemion.principals p
      ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
    WHERE k.token_hash=token AND k.revoked_at IS NULL AND p.disabled_at IS NULL
      AND (k.expires_at IS NULL OR k.expires_at > now())
$$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mnemion FROM PUBLIC;
GRANT USAGE ON SCHEMA mnemion TO mnemion_app, mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.tenant(), mnemion.principal(),
    mnemion.administrator(), mnemion.authorized(uuid, integer), mnemion.authenticate(text)
    TO mnemion_app, mnemion_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA mnemion TO mnemion_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA mnemion TO mnemion_worker;
REVOKE INSERT, UPDATE, DELETE ON mnemion.tenants, mnemion.embedding_generations FROM mnemion_app;
REVOKE UPDATE, DELETE ON mnemion.source_revisions, mnemion.memory_revisions,
    mnemion.core_block_revisions FROM mnemion_app;

ALTER TABLE mnemion.tenants ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON mnemion.tenants TO mnemion_app
    USING (id=mnemion.tenant());
ALTER TABLE mnemion.principals ENABLE ROW LEVEL SECURITY;
CREATE POLICY principal_scope ON mnemion.principals TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (id=mnemion.principal() OR mnemion.administrator()))
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator());
ALTER TABLE mnemion.api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY key_scope ON mnemion.api_keys TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (principal_id=mnemion.principal() OR mnemion.administrator()))
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator());
ALTER TABLE mnemion.spaces ENABLE ROW LEVEL SECURITY;
CREATE POLICY space_scope ON mnemion.spaces TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (mnemion.authorized(id) OR mnemion.administrator()))
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.administrator());
ALTER TABLE mnemion.space_grants ENABLE ROW LEVEL SECURITY;
CREATE POLICY grant_scope ON mnemion.space_grants TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (principal_id=mnemion.principal() OR mnemion.administrator() OR mnemion.authorized(space_id, 40)))
    WITH CHECK (tenant_id=mnemion.tenant() AND (mnemion.administrator() OR mnemion.authorized(space_id, 40)));

DO $policies$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY[
        'sources', 'source_revisions', 'memories', 'memory_revisions', 'embeddings',
        'operations', 'jobs', 'idempotency_keys', 'core_blocks', 'core_block_revisions', 'legacy_aliases', 'deletion_receipts'
    ] LOOP
        EXECUTE format('ALTER TABLE mnemion.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format(
            'CREATE POLICY read_scope ON mnemion.%I FOR SELECT TO mnemion_app USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id))',
            tab);
        EXECUTE format(
            'CREATE POLICY write_scope ON mnemion.%I FOR ALL TO mnemion_app USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id, 20)) WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id, 20))',
            tab);
        EXECUTE format(
            'CREATE POLICY worker_scope ON mnemion.%I TO mnemion_worker USING (tenant_id=mnemion.tenant()) WITH CHECK (tenant_id=mnemion.tenant())',
            tab);
    END LOOP;
END
$policies$;
ALTER TABLE mnemion.audit_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_read ON mnemion.audit_events FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.administrator());
CREATE POLICY audit_append ON mnemion.audit_events FOR INSERT TO mnemion_app
    WITH CHECK (tenant_id=mnemion.tenant() AND principal_id=mnemion.principal());
REVOKE UPDATE, DELETE ON mnemion.audit_events FROM mnemion_app, mnemion_worker;

CREATE FUNCTION mnemion.claim_job(lease uuid, seconds integer, generation text)
    RETURNS SETOF mnemion.jobs
    LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE mnemion.jobs SET state='leased', lease_id=lease,
        lease_until=now()+make_interval(secs=>greatest(5, least(seconds, 3600))),
        attempts=attempts+1
    WHERE (tenant_id, space_id, id) = (
        SELECT tenant_id, space_id, id FROM mnemion.jobs
        WHERE ((state='pending' AND available_at <= now())
           OR (state='leased' AND lease_until < now()))
          AND (kind='purge' OR generation_id=generation)
        ORDER BY available_at, created_at, id
        FOR UPDATE SKIP LOCKED LIMIT 1
    )
    RETURNING *
$$;
REVOKE ALL ON FUNCTION mnemion.claim_job(uuid, integer, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.claim_job(uuid, integer, text) TO mnemion_worker;
