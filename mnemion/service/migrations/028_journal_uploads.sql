-- Private staging is separate from searchable memories and source grants.
-- Upload rows contain no executable paths and confer no authority after revocation.
CREATE TABLE mnemion.journal_uploads (
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    id uuid NOT NULL,
    space_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK (version>0),
    state text NOT NULL DEFAULT 'uploading'
        CHECK (state IN ('uploading','reviewing','reviewed','restoring','completed','cancelled')),
    identity_mode text NOT NULL CHECK (identity_mode IN ('original','copy')),
    namespace text NOT NULL,
    catalog_schema integer NOT NULL CHECK (catalog_schema IN (1,2)),
    reject_personal_data boolean NOT NULL DEFAULT true,
    declaration_sha256 text NOT NULL CHECK (declaration_sha256 ~ '^[a-f0-9]{64}$'),
    input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[a-f0-9]{64}$'),
    preview_sha256 text CHECK (preview_sha256 ~ '^[a-f0-9]{64}$'),
    total_bytes bigint NOT NULL CHECK (total_bytes BETWEEN 0 AND 2147483648),
    received bigint NOT NULL DEFAULT 0 CHECK (received>=0 AND received<=total_bytes),
    files integer NOT NULL CHECK (files BETWEEN 0 AND 8192),
    completed_files integer NOT NULL DEFAULT 0 CHECK (completed_files BETWEEN 0 AND files),
    expected_records bigint NOT NULL CHECK (expected_records BETWEEN 0 AND 1000000),
    records bigint NOT NULL DEFAULT 0 CHECK (records BETWEEN 0 AND 1000000),
    physical_records bigint NOT NULL DEFAULT 0 CHECK (physical_records BETWEEN 0 AND 1000000),
    duplicates bigint NOT NULL DEFAULT 0 CHECK (duplicates>=0),
    identities bigint NOT NULL DEFAULT 0 CHECK (identities BETWEEN 0 AND 100000),
    reviewed_identities bigint NOT NULL DEFAULT 0 CHECK (reviewed_identities>=0),
    processed_identities bigint NOT NULL DEFAULT 0 CHECK (processed_identities>=0),
    reviewed_batches integer NOT NULL DEFAULT 0 CHECK (reviewed_batches>=0),
    applied_batches integer NOT NULL DEFAULT 0 CHECK (applied_batches BETWEEN 0 AND reviewed_batches),
    review_priority integer NOT NULL DEFAULT -1 CHECK (review_priority BETWEEN -1 AND 1),
    review_cursor uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    counts jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(counts)='object'),
    applied_counts jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(applied_counts)='object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '24 hours',
    PRIMARY KEY(tenant_id,id),
    FOREIGN KEY(tenant_id,space_id) REFERENCES mnemion.spaces(tenant_id,id),
    FOREIGN KEY(tenant_id,principal_id) REFERENCES mnemion.principals(tenant_id,id)
);
CREATE INDEX journal_upload_expiry ON mnemion.journal_uploads(expires_at);
CREATE INDEX journal_upload_owner ON mnemion.journal_uploads(tenant_id,principal_id,space_id,created_at);

CREATE TABLE mnemion.journal_upload_files (
    tenant_id uuid NOT NULL,
    upload_id uuid NOT NULL,
    file_index integer NOT NULL CHECK (file_index BETWEEN 0 AND 8191),
    path text NOT NULL CHECK (length(path) BETWEEN 1 AND 120),
    total_bytes bigint NOT NULL CHECK (total_bytes BETWEEN 0 AND 2147483648),
    received bigint NOT NULL DEFAULT 0 CHECK (received BETWEEN 0 AND total_bytes),
    transport_sha256 text NOT NULL DEFAULT repeat('0',64) CHECK (transport_sha256 ~ '^[a-f0-9]{64}$'),
    tail bytea NOT NULL DEFAULT '' CHECK (octet_length(tail)<=393216),
    complete boolean NOT NULL DEFAULT false,
    PRIMARY KEY(tenant_id,upload_id,file_index),
    UNIQUE(tenant_id,upload_id,path),
    FOREIGN KEY(tenant_id,upload_id) REFERENCES mnemion.journal_uploads(tenant_id,id) ON DELETE CASCADE
);

CREATE TABLE mnemion.journal_upload_chunks (
    tenant_id uuid NOT NULL,
    upload_id uuid NOT NULL,
    file_index integer NOT NULL,
    file_offset bigint NOT NULL CHECK (file_offset>=0),
    bytes integer NOT NULL CHECK (bytes BETWEEN 1 AND 262144),
    sha256 text NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY(tenant_id,upload_id,file_index,file_offset),
    FOREIGN KEY(tenant_id,upload_id,file_index)
        REFERENCES mnemion.journal_upload_files(tenant_id,upload_id,file_index) ON DELETE CASCADE
);

-- Canonical hashes retain complete event/version conflict detection without
-- storing every historical body or the incoming binary transport a second time.
CREATE TABLE mnemion.journal_upload_events (
    tenant_id uuid NOT NULL,
    upload_id uuid NOT NULL,
    event_id uuid NOT NULL,
    original_id uuid NOT NULL,
    source_version bigint NOT NULL CHECK (source_version BETWEEN 1 AND 9007199254740991),
    digest text NOT NULL CHECK (digest ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY(tenant_id,upload_id,event_id),
    UNIQUE(tenant_id,upload_id,original_id,source_version),
    FOREIGN KEY(tenant_id,upload_id) REFERENCES mnemion.journal_uploads(tenant_id,id) ON DELETE CASCADE
);

CREATE TABLE mnemion.journal_upload_latest (
    tenant_id uuid NOT NULL,
    upload_id uuid NOT NULL,
    original_id uuid NOT NULL,
    source_version bigint NOT NULL CHECK (source_version BETWEEN 0 AND 9007199254740991),
    denied boolean NOT NULL,
    action text CHECK (action IN ('upsert','forget','quarantine')),
    priority integer NOT NULL CHECK (priority IN (0,1)),
    line bytea CHECK (octet_length(line)<=393216),
    CHECK (line IS NOT NULL OR denied),
    PRIMARY KEY(tenant_id,upload_id,original_id),
    FOREIGN KEY(tenant_id,upload_id) REFERENCES mnemion.journal_uploads(tenant_id,id) ON DELETE CASCADE
);
CREATE INDEX journal_upload_review_order
    ON mnemion.journal_upload_latest(tenant_id,upload_id,priority,original_id);

CREATE TABLE mnemion.journal_upload_batches (
    tenant_id uuid NOT NULL,
    upload_id uuid NOT NULL,
    batch_index integer NOT NULL CHECK (batch_index>=0),
    priority integer NOT NULL CHECK (priority IN (0,1)),
    first_id uuid NOT NULL,
    last_id uuid NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    items jsonb NOT NULL CHECK (jsonb_typeof(items)='array' AND jsonb_array_length(items) BETWEEN 1 AND 64),
    applied boolean NOT NULL DEFAULT false,
    PRIMARY KEY(tenant_id,upload_id,batch_index),
    FOREIGN KEY(tenant_id,upload_id) REFERENCES mnemion.journal_uploads(tenant_id,id) ON DELETE CASCADE
);

ALTER TABLE mnemion.journal_uploads ENABLE ROW LEVEL SECURITY;
CREATE POLICY journal_upload_owner ON mnemion.journal_uploads FOR ALL TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND principal_id=mnemion.principal()
        AND mnemion.administrator() AND mnemion.authorized(space_id,40))
    WITH CHECK (tenant_id=mnemion.tenant() AND principal_id=mnemion.principal()
        AND mnemion.administrator() AND mnemion.authorized(space_id,40));
GRANT SELECT,INSERT,UPDATE,DELETE ON mnemion.journal_uploads TO mnemion_app;

DO $$ DECLARE table_name text; BEGIN
    FOREACH table_name IN ARRAY ARRAY['journal_upload_files','journal_upload_chunks',
        'journal_upload_events','journal_upload_latest','journal_upload_batches'] LOOP
        EXECUTE format('ALTER TABLE mnemion.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON mnemion.%I TO mnemion_app', table_name);
        EXECUTE format('CREATE POLICY journal_upload_owner ON mnemion.%I FOR ALL TO mnemion_app
            USING (tenant_id=mnemion.tenant() AND EXISTS (
                SELECT FROM mnemion.journal_uploads u WHERE u.tenant_id=%I.tenant_id AND u.id=%I.upload_id))
            WITH CHECK (tenant_id=mnemion.tenant() AND EXISTS (
                SELECT FROM mnemion.journal_uploads u WHERE u.tenant_id=%I.tenant_id AND u.id=%I.upload_id))',
            table_name,table_name,table_name,table_name,table_name);
    END LOOP;
END $$;

-- Small cleanup steps do not load large content into a worker or require the
-- original uploader to return. The worker can delete only already-expired staging.
CREATE FUNCTION mnemion.expire_journal_upload() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE selected record; affected integer; total integer := 0; table_name text; maximum integer;
BEGIN
    SELECT tenant_id,id INTO selected FROM mnemion.journal_uploads
        WHERE expires_at<clock_timestamp() ORDER BY expires_at
        FOR UPDATE SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN 0; END IF;
    FOREACH table_name IN ARRAY ARRAY['journal_upload_batches','journal_upload_latest',
        'journal_upload_events','journal_upload_chunks','journal_upload_files'] LOOP
        maximum := CASE WHEN table_name IN ('journal_upload_latest','journal_upload_files') THEN 32 ELSE 1000 END;
        IF table_name='journal_upload_files' THEN
            DELETE FROM mnemion.journal_upload_files f WHERE f.ctid IN (
                SELECT pending.ctid FROM mnemion.journal_upload_files pending
                WHERE pending.tenant_id=selected.tenant_id AND pending.upload_id=selected.id
                AND NOT EXISTS (SELECT FROM mnemion.journal_upload_chunks c
                    WHERE c.tenant_id=pending.tenant_id AND c.upload_id=pending.upload_id
                        AND c.file_index=pending.file_index)
                LIMIT 32);
        ELSE
            EXECUTE format('DELETE FROM mnemion.%I WHERE ctid IN (
                SELECT ctid FROM mnemion.%I WHERE tenant_id=$1 AND upload_id=$2 LIMIT $3)',table_name,table_name)
                USING selected.tenant_id,selected.id,maximum;
        END IF;
        GET DIAGNOSTICS affected = ROW_COUNT;
        total := total+affected;
    END LOOP;
    IF total=0 THEN
        DELETE FROM mnemion.journal_uploads WHERE tenant_id=selected.tenant_id AND id=selected.id;
        RETURN 1;
    END IF;
    RETURN total;
END $$;
REVOKE ALL ON FUNCTION mnemion.expire_journal_upload() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.expire_journal_upload() TO mnemion_worker;

-- Count this owner's retained staging even after a space grant was revoked.
-- Return only capacity, never identities or another principal's usage.
CREATE FUNCTION mnemion.journal_upload_capacity(incoming_bytes bigint) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT mnemion.administrator() AND incoming_bytes BETWEEN 0 AND 2147483648
        AND count(*)<8
        AND count(*) FILTER (WHERE state NOT IN ('completed','cancelled') AND expires_at>now())<2
        AND coalesce(sum(total_bytes),0)+incoming_bytes<=4294967296
    FROM mnemion.journal_uploads
    WHERE tenant_id=mnemion.tenant() AND principal_id=mnemion.principal()
$$;
REVOKE ALL ON FUNCTION mnemion.journal_upload_capacity(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.journal_upload_capacity(bigint) TO mnemion_app;
