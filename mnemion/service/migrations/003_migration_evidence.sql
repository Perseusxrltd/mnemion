-- Offline migration maps one explicitly owned legacy profile to one private
-- space. Content-bearing evidence uses the same scope and erasure lifecycle.
CREATE TABLE mnemion.space_fences (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    token uuid NOT NULL,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, space_id),
    FOREIGN KEY (tenant_id, space_id) REFERENCES mnemion.spaces(tenant_id, id)
);
CREATE TABLE mnemion.legacy_profiles (
    tenant_id uuid NOT NULL,
    profile_id text NOT NULL,
    space_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    state text NOT NULL DEFAULT 'importing' CHECK (state IN ('importing','active','rollback')),
    last_snapshot_at timestamptz,
    backup_id text,
    cutover_at timestamptz,
    report jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (tenant_id, profile_id),
    UNIQUE (tenant_id, space_id),
    FOREIGN KEY (tenant_id, space_id) REFERENCES mnemion.spaces(tenant_id, id),
    FOREIGN KEY (tenant_id, owner_id) REFERENCES mnemion.principals(tenant_id, id)
);
CREATE TABLE mnemion.legacy_records (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    collection_id text NOT NULL,
    collection_name text NOT NULL,
    legacy_id text NOT NULL,
    memory_id uuid NOT NULL,
    fingerprint text NOT NULL,
    imported_version integer NOT NULL,
    PRIMARY KEY (tenant_id, space_id, collection_id, legacy_id),
    FOREIGN KEY (tenant_id, space_id, memory_id) REFERENCES mnemion.memories(tenant_id, space_id, id)
);
CREATE TABLE mnemion.legacy_blocks (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    key text NOT NULL,
    fingerprint text NOT NULL,
    imported_version integer NOT NULL,
    PRIMARY KEY (tenant_id, space_id, key),
    FOREIGN KEY (tenant_id, space_id, key) REFERENCES mnemion.core_blocks(tenant_id, space_id, key)
);
CREATE TABLE mnemion.source_attachments (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    id uuid NOT NULL,
    source_revision_id uuid NOT NULL,
    name text NOT NULL,
    media_type text NOT NULL DEFAULT 'application/octet-stream',
    content bytea NOT NULL,
    content_hash text NOT NULL,
    PRIMARY KEY (tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, space_id, source_revision_id)
        REFERENCES mnemion.source_revisions(tenant_id, space_id, id) ON DELETE CASCADE
);
ALTER TABLE mnemion.space_fences ENABLE ROW LEVEL SECURITY;
ALTER TABLE mnemion.legacy_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE mnemion.legacy_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE mnemion.legacy_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE mnemion.source_attachments ENABLE ROW LEVEL SECURITY;
GRANT SELECT ON mnemion.space_fences, mnemion.legacy_profiles,
    mnemion.legacy_records, mnemion.legacy_blocks, mnemion.source_attachments TO mnemion_app;
GRANT SELECT, DELETE ON mnemion.source_attachments TO mnemion_worker;
CREATE POLICY fence_read ON mnemion.space_fences FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id));
CREATE POLICY profile_read ON mnemion.legacy_profiles FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id, 40));
CREATE POLICY legacy_record_read ON mnemion.legacy_records FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id, 30));
CREATE POLICY legacy_block_read ON mnemion.legacy_blocks FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id, 30));
CREATE POLICY attachment_read ON mnemion.source_attachments FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id));
CREATE POLICY attachment_worker ON mnemion.source_attachments TO mnemion_worker
    USING (tenant_id=mnemion.tenant()) WITH CHECK (tenant_id=mnemion.tenant());
