-- Hosted OAuth reuses password-session anchors, rotation and recovery policy.
-- Client metadata is public registration data; proofs and token digests are
-- available only through bounded authentication functions, never memory queries.
CREATE TABLE mnemion.oauth_local_attempts (
    subject text PRIMARY KEY CHECK (subject='global' OR subject ~ '^[0-9a-f]{64}$'),
    started_at timestamptz NOT NULL,
    attempts integer NOT NULL CHECK (attempts BETWEEN 1 AND 2401)
);
ALTER TABLE mnemion.oauth_local_attempts ENABLE ROW LEVEL SECURITY;
CREATE FUNCTION mnemion.local_oauth_admit(subject_hash text,maximum integer) RETURNS boolean
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE instant timestamptz := clock_timestamp(); total integer; per_subject integer;
BEGIN
    IF subject_hash IS NULL OR subject_hash !~ '^[0-9a-f]{64}$' OR maximum NOT BETWEEN 1 AND 120
      THEN RETURN false; END IF;
    PERFORM pg_advisory_xact_lock(731293284018);
    DELETE FROM mnemion.oauth_local_attempts WHERE started_at<=instant-interval '2 minutes';
    INSERT INTO mnemion.oauth_local_attempts VALUES('global',instant,1)
      ON CONFLICT(subject) DO UPDATE SET
        started_at=CASE WHEN mnemion.oauth_local_attempts.started_at<=instant-interval '1 minute'
          THEN instant ELSE mnemion.oauth_local_attempts.started_at END,
        attempts=CASE WHEN mnemion.oauth_local_attempts.started_at<=instant-interval '1 minute'
          THEN 1 ELSE least(2401,mnemion.oauth_local_attempts.attempts+1) END
      RETURNING attempts INTO total;
    IF total>2400 OR (SELECT count(*) FROM mnemion.oauth_local_attempts)>=8192 THEN RETURN false; END IF;
    INSERT INTO mnemion.oauth_local_attempts VALUES(subject_hash,instant,1)
      ON CONFLICT(subject) DO UPDATE SET
        started_at=CASE WHEN mnemion.oauth_local_attempts.started_at<=instant-interval '1 minute'
          THEN instant ELSE mnemion.oauth_local_attempts.started_at END,
        attempts=CASE WHEN mnemion.oauth_local_attempts.started_at<=instant-interval '1 minute'
          THEN 1 ELSE least(2401,mnemion.oauth_local_attempts.attempts+1) END
      RETURNING attempts INTO per_subject;
    RETURN per_subject<=maximum;
END $$;
CREATE TABLE mnemion.oauth_local_clients (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f-]{36}$'),
    metadata jsonb NOT NULL CHECK (jsonb_typeof(metadata)='object' AND pg_column_size(metadata)<=32768),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE mnemion.oauth_local_requests (
    id uuid PRIMARY KEY,
    ticket_hash text NOT NULL UNIQUE CHECK (ticket_hash ~ '^[0-9a-f]{64}$'),
    client_id text NOT NULL REFERENCES mnemion.oauth_local_clients(id),
    parameters jsonb NOT NULL CHECK (pg_column_size(parameters)<=16384),
    issuer text NOT NULL CHECK (length(issuer)<=2048),
    resource text NOT NULL CHECK (length(resource)<=2048),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    tenant_id uuid,
    principal_id uuid,
    account_version uuid,
    proof_hash text CHECK (proof_hash ~ '^[0-9a-f]{64}$'),
    browser_hash text CHECK (browser_hash ~ '^[0-9a-f]{64}$'),
    permissions jsonb,
    code_hash text UNIQUE CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    code_expires_at timestamptz,
    consumed_at timestamptz,
    session_id uuid REFERENCES mnemion.sign_in_sessions(id) ON DELETE SET NULL
);
CREATE INDEX oauth_local_request_expiry ON mnemion.oauth_local_requests(expires_at);
CREATE TABLE mnemion.oauth_local_connections (
    session_id uuid PRIMARY KEY REFERENCES mnemion.sign_in_sessions(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    client_id text NOT NULL REFERENCES mnemion.oauth_local_clients(id),
    issuer text NOT NULL,
    resource text NOT NULL,
    scopes text[] NOT NULL CHECK (scopes=ARRAY['mnemion:access']),
    FOREIGN KEY (tenant_id,principal_id) REFERENCES mnemion.principals(tenant_id,id)
);
ALTER TABLE mnemion.oauth_local_clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE mnemion.oauth_local_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE mnemion.oauth_local_connections ENABLE ROW LEVEL SECURITY;
GRANT SELECT ON mnemion.oauth_local_connections TO mnemion_app;
CREATE POLICY oauth_connection_read ON mnemion.oauth_local_connections FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (principal_id=mnemion.principal() OR mnemion.administrator()));

CREATE FUNCTION mnemion.local_oauth_client(client text) RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT metadata FROM mnemion.oauth_local_clients WHERE id=client
$$;
CREATE FUNCTION mnemion.local_oauth_register(client text,value jsonb) RETURNS boolean
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(731293284016);
    IF (SELECT count(*) FROM mnemion.oauth_local_clients)>=10000 THEN RETURN false; END IF;
    INSERT INTO mnemion.oauth_local_clients(id,metadata) VALUES(client,value);
    RETURN true;
END $$;
CREATE FUNCTION mnemion.local_oauth_begin(
    request_id uuid,ticket text,client text,params jsonb,expected_issuer text,expected_resource text
) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(731293284017);
    DELETE FROM mnemion.oauth_local_requests WHERE expires_at<clock_timestamp()-interval '1 hour';
    IF (SELECT count(*) FROM mnemion.oauth_local_requests WHERE expires_at>clock_timestamp())>=2048
      THEN RETURN false; END IF;
    INSERT INTO mnemion.oauth_local_requests
      (id,ticket_hash,client_id,parameters,issuer,resource,expires_at)
      VALUES(request_id,ticket,client,params,expected_issuer,expected_resource,
        clock_timestamp()+interval '10 minutes');
    RETURN true;
END $$;
CREATE FUNCTION mnemion.local_oauth_request(ticket text,expected_issuer text,expected_resource text)
    RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('id',r.id,'client_id',r.client_id,'parameters',r.parameters,
      'client_name',c.metadata->>'client_name','expires_at',r.expires_at)
    FROM mnemion.oauth_local_requests r JOIN mnemion.oauth_local_clients c ON c.id=r.client_id
    WHERE r.ticket_hash=ticket AND r.issuer=expected_issuer AND r.resource=expected_resource
      AND r.expires_at>clock_timestamp() AND r.code_hash IS NULL AND r.consumed_at IS NULL
$$;

-- Display the exact current grants before approval. A change requires a fresh
-- permission review; a browser cannot approve a stale or substituted account.
CREATE FUNCTION mnemion._local_oauth_permissions(workspace uuid,person uuid) RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    WITH grants AS MATERIALIZED (
      SELECT s.id,s.name,g.role FROM mnemion.space_grants g JOIN mnemion.spaces s
        ON s.tenant_id=g.tenant_id AND s.id=g.space_id
      WHERE g.tenant_id=workspace AND g.principal_id=person
    ), summary AS (
      SELECT count(*) AS total,
        encode(sha256(convert_to(coalesce(string_agg(jsonb_build_array(id,name,role)::text,E'\n' ORDER BY id),''),'UTF8')),'hex') AS revision
      FROM grants
    )
    SELECT jsonb_build_object('principal_id',p.id,'name',p.name,'workspace_name',t.name,
      'administrator',p.administrator,'space_count',summary.total,'grant_revision',summary.revision,
      'spaces',coalesce((SELECT jsonb_agg(jsonb_build_object('id',g.id,'name',g.name,'role',g.role) ORDER BY g.id)
        FROM (SELECT * FROM grants ORDER BY id LIMIT 200) g),'[]'::jsonb))
    FROM mnemion.principals p JOIN mnemion.tenants t ON t.id=p.tenant_id
    CROSS JOIN summary
    WHERE p.tenant_id=workspace AND p.id=person AND p.disabled_at IS NULL
$$;
CREATE FUNCTION mnemion.local_oauth_login(
    ticket text,expected_issuer text,expected_resource text,workspace uuid,person uuid,
    expected_verifier text,expected_version uuid,proof text,browser text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE request mnemion.oauth_local_requests%ROWTYPE; preview jsonb;
BEGIN
    PERFORM mnemion._sign_in_lock(workspace);
    SELECT * INTO request FROM mnemion.oauth_local_requests
      WHERE ticket_hash=ticket AND issuer=expected_issuer AND resource=expected_resource FOR UPDATE;
    IF NOT FOUND OR request.expires_at<=clock_timestamp() OR request.code_hash IS NOT NULL
      OR request.consumed_at IS NOT NULL THEN RETURN NULL; END IF;
    IF NOT EXISTS (SELECT FROM mnemion.password_accounts a JOIN mnemion.principals p
      ON p.tenant_id=a.tenant_id AND p.id=a.principal_id
      WHERE a.tenant_id=workspace AND a.principal_id=person AND a.password_hash=expected_verifier
        AND a.version=expected_version AND NOT a.reset_required AND p.disabled_at IS NULL
        AND p.kind='human') THEN RETURN NULL; END IF;
    preview := mnemion._local_oauth_permissions(workspace,person);
    UPDATE mnemion.oauth_local_requests SET tenant_id=workspace,principal_id=person,
      account_version=expected_version,proof_hash=proof,browser_hash=browser,permissions=preview
      WHERE id=request.id;
    RETURN preview;
END $$;
CREATE FUNCTION mnemion.local_oauth_consent(
    ticket text,expected_issuer text,expected_resource text,proof text,browser text,code text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE request mnemion.oauth_local_requests%ROWTYPE; preview jsonb;
BEGIN
    SELECT * INTO request FROM mnemion.oauth_local_requests
      WHERE ticket_hash=ticket AND issuer=expected_issuer AND resource=expected_resource;
    IF NOT FOUND OR request.tenant_id IS NULL THEN RETURN NULL; END IF;
    PERFORM mnemion._sign_in_lock(request.tenant_id);
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE id=request.id FOR UPDATE;
    IF request.expires_at<=clock_timestamp() OR request.code_hash IS NOT NULL
      OR request.consumed_at IS NOT NULL OR request.proof_hash IS DISTINCT FROM proof
      OR request.browser_hash IS DISTINCT FROM browser THEN RETURN NULL; END IF;
    IF NOT EXISTS (SELECT FROM mnemion.password_accounts a JOIN mnemion.principals p
      ON p.tenant_id=a.tenant_id AND p.id=a.principal_id
      WHERE a.tenant_id=request.tenant_id AND a.principal_id=request.principal_id
        AND a.version=request.account_version AND NOT a.reset_required AND p.disabled_at IS NULL)
      THEN RETURN NULL; END IF;
    preview := mnemion._local_oauth_permissions(request.tenant_id,request.principal_id);
    IF preview IS DISTINCT FROM request.permissions THEN RETURN NULL; END IF;
    UPDATE mnemion.oauth_local_requests SET code_hash=code,
      code_expires_at=clock_timestamp()+interval '2 minutes',proof_hash=NULL,browser_hash=NULL
      WHERE id=request.id;
    PERFORM mnemion._sign_in_audit(request.tenant_id,request.principal_id,'oauth.consent',request.id);
    RETURN request.parameters;
END $$;
CREATE FUNCTION mnemion.local_oauth_cancel(
    ticket text,expected_issuer text,expected_resource text,browser text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE params jsonb;
BEGIN
    DELETE FROM mnemion.oauth_local_requests r WHERE r.ticket_hash=ticket
      AND r.issuer=expected_issuer AND r.resource=expected_resource AND r.code_hash IS NULL
      AND r.consumed_at IS NULL AND r.expires_at>clock_timestamp()
      AND (r.browser_hash IS NULL OR r.browser_hash=browser) RETURNING parameters INTO params;
    RETURN params;
END $$;
CREATE FUNCTION mnemion.local_oauth_code(code text,client text,expected_issuer text,expected_resource text)
    RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('id',r.id,'client_id',r.client_id,'parameters',r.parameters,
      'expires_at',extract(epoch FROM r.code_expires_at),'subject',r.principal_id)
    FROM mnemion.oauth_local_requests r
    WHERE r.code_hash=code AND r.client_id=client AND r.issuer=expected_issuer
      AND r.resource=expected_resource AND r.code_expires_at>clock_timestamp()
$$;
CREATE FUNCTION mnemion.local_oauth_exchange(
    code text,client text,expected_issuer text,expected_resource text,session_uuid uuid,key_uuid uuid,
    anchor_hash text,access_digest text,refresh_digest text,label text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE request mnemion.oauth_local_requests%ROWTYPE; account mnemion.password_accounts%ROWTYPE;
  issued mnemion.sign_in_sessions%ROWTYPE;
BEGIN
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE code_hash=code AND client_id=client
      AND issuer=expected_issuer AND resource=expected_resource;
    IF NOT FOUND OR request.tenant_id IS NULL THEN RETURN NULL; END IF;
    PERFORM mnemion._sign_in_lock(request.tenant_id);
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE id=request.id FOR UPDATE;
    IF request.code_expires_at<=clock_timestamp() THEN RETURN NULL; END IF;
    IF request.consumed_at IS NOT NULL THEN
      UPDATE mnemion.api_keys k SET revoked_at=coalesce(k.revoked_at,clock_timestamp())
        FROM mnemion.sign_in_sessions s WHERE s.id=request.session_id AND k.id=s.key_id;
      RETURN jsonb_build_object('error','code_reused');
    END IF;
    SELECT * INTO account FROM mnemion.password_accounts a WHERE a.tenant_id=request.tenant_id
      AND a.principal_id=request.principal_id AND a.version=request.account_version AND NOT a.reset_required;
    IF NOT FOUND OR mnemion._local_oauth_permissions(request.tenant_id,request.principal_id)
      IS DISTINCT FROM request.permissions THEN RETURN NULL; END IF;
    SELECT * INTO issued FROM mnemion.issue_password_session(request.tenant_id,request.principal_id,
      account.password_hash,account.version,session_uuid,key_uuid,anchor_hash,access_digest,
      refresh_digest,NULL,label,'native');
    IF NOT FOUND THEN RETURN NULL; END IF;
    INSERT INTO mnemion.oauth_local_connections(session_id,tenant_id,principal_id,client_id,issuer,resource,scopes)
      VALUES(issued.id,issued.tenant_id,issued.principal_id,client,expected_issuer,expected_resource,ARRAY['mnemion:access']);
    UPDATE mnemion.oauth_local_requests SET consumed_at=clock_timestamp(),session_id=issued.id WHERE id=request.id;
    RETURN jsonb_build_object('session_id',issued.id,'access_expires_at',extract(epoch FROM issued.access_expires_at),
      'expires_at',extract(epoch FROM issued.expires_at));
END $$;

CREATE FUNCTION mnemion.local_oauth_token(digest text,token_kind text,expected_issuer text,expected_resource text)
    RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('session_id',s.id,'tenant_id',s.tenant_id,'principal_id',s.principal_id,
      'key_id',s.key_id,'client_id',c.client_id,'scopes',c.scopes,
      'expires_at',extract(epoch FROM CASE WHEN token_kind='access' THEN s.access_expires_at ELSE s.expires_at END))
    FROM mnemion.oauth_local_connections c JOIN mnemion.sign_in_sessions s ON s.id=c.session_id
    JOIN mnemion.api_keys k ON k.id=s.key_id AND k.tenant_id=s.tenant_id
    JOIN mnemion.password_accounts a ON a.tenant_id=s.tenant_id AND a.principal_id=s.principal_id
    JOIN mnemion.principals p ON p.tenant_id=s.tenant_id AND p.id=s.principal_id
    WHERE c.issuer=expected_issuer AND c.resource=expected_resource AND s.expires_at>clock_timestamp()
      AND k.revoked_at IS NULL AND k.expires_at>clock_timestamp() AND k.session_key
      AND p.disabled_at IS NULL AND NOT a.reset_required AND a.version=s.account_version
      AND ((token_kind='access' AND s.access_hash=digest AND s.access_expires_at>clock_timestamp())
        OR (token_kind='refresh' AND (s.refresh_hash=digest OR EXISTS
          (SELECT FROM mnemion.spent_refresh_tokens h WHERE h.session_id=s.id AND h.token_hash=digest))))
$$;
CREATE FUNCTION mnemion.local_oauth_refresh(
    previous_refresh text,client text,expected_issuer text,expected_resource text,access_digest text,refresh_digest text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE token jsonb; rotated record;
BEGIN
    token := mnemion.local_oauth_token(previous_refresh,'refresh',expected_issuer,expected_resource);
    IF token IS NULL OR token->>'client_id'<>client THEN RETURN NULL; END IF;
    SELECT * INTO rotated FROM mnemion.rotate_password_session(previous_refresh,access_digest,refresh_digest,
      NULL,'native',(token->>'tenant_id')::uuid,(token->>'session_id')::uuid);
    IF rotated.result IS DISTINCT FROM 'ok' THEN RETURN jsonb_build_object('error','invalid_refresh'); END IF;
    RETURN jsonb_build_object('session_id',rotated.session_id,
      'access_expires_at',extract(epoch FROM rotated.access_expires_at),'expires_at',extract(epoch FROM rotated.expires_at));
END $$;
CREATE FUNCTION mnemion.local_oauth_revoke(
    digest text,kind text,client text,expected_issuer text,expected_resource text
) RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE token jsonb;
BEGIN
    token := mnemion.local_oauth_token(digest,kind,expected_issuer,expected_resource);
    IF token IS NULL OR token->>'client_id'<>client THEN RETURN; END IF;
    PERFORM mnemion._sign_in_lock((token->>'tenant_id')::uuid);
    UPDATE mnemion.api_keys SET revoked_at=coalesce(revoked_at,clock_timestamp()) WHERE id=(token->>'key_id')::uuid;
    PERFORM mnemion._sign_in_audit((token->>'tenant_id')::uuid,(token->>'principal_id')::uuid,
      'oauth.revoked',(token->>'session_id')::uuid);
END $$;

REVOKE ALL ON FUNCTION mnemion._local_oauth_permissions(uuid,uuid) FROM PUBLIC,mnemion_app,mnemion_worker;
REVOKE ALL ON FUNCTION mnemion.local_oauth_client(text),mnemion.local_oauth_register(text,jsonb),
    mnemion.local_oauth_admit(text,integer),
    mnemion.local_oauth_cancel(text,text,text,text),
    mnemion.local_oauth_begin(uuid,text,text,jsonb,text,text),mnemion.local_oauth_request(text,text,text),
    mnemion.local_oauth_login(text,text,text,uuid,uuid,text,uuid,text,text),
    mnemion.local_oauth_consent(text,text,text,text,text,text),mnemion.local_oauth_code(text,text,text,text),
    mnemion.local_oauth_exchange(text,text,text,text,uuid,uuid,text,text,text,text),
    mnemion.local_oauth_token(text,text,text,text),mnemion.local_oauth_refresh(text,text,text,text,text,text),
    mnemion.local_oauth_revoke(text,text,text,text,text)
    FROM PUBLIC,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.local_oauth_client(text),mnemion.local_oauth_register(text,jsonb),
    mnemion.local_oauth_admit(text,integer),
    mnemion.local_oauth_cancel(text,text,text,text),
    mnemion.local_oauth_begin(uuid,text,text,jsonb,text,text),mnemion.local_oauth_request(text,text,text),
    mnemion.local_oauth_login(text,text,text,uuid,uuid,text,uuid,text,text),
    mnemion.local_oauth_consent(text,text,text,text,text,text),mnemion.local_oauth_code(text,text,text,text),
    mnemion.local_oauth_exchange(text,text,text,text,uuid,uuid,text,text,text,text),
    mnemion.local_oauth_token(text,text,text,text),mnemion.local_oauth_refresh(text,text,text,text,text,text),
    mnemion.local_oauth_revoke(text,text,text,text,text)
    TO mnemion_app;
