-- Password accounts are separate from principals and never grant memory access.
-- Session anchors retain one identity across refreshes and are never exported.
ALTER TABLE mnemion.api_keys ADD COLUMN session_key boolean NOT NULL DEFAULT false;
CREATE OR REPLACE FUNCTION mnemion.authenticate(token text)
    RETURNS TABLE(tenant_id uuid, principal_id uuid, key_id uuid, administrator boolean)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT k.tenant_id,k.principal_id,k.id,p.administrator
    FROM mnemion.api_keys k JOIN mnemion.principals p
      ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
    WHERE k.token_hash=token AND NOT k.session_key AND k.revoked_at IS NULL AND p.disabled_at IS NULL
      AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())
$$;

CREATE TABLE mnemion.password_accounts (
    tenant_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    username text NOT NULL CHECK (length(username) BETWEEN 3 AND 128),
    password_hash text NOT NULL CHECK (length(password_hash) BETWEEN 1 AND 200),
    version uuid NOT NULL,
    reset_required boolean NOT NULL DEFAULT false,
    changed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, principal_id),
    UNIQUE (tenant_id, username),
    FOREIGN KEY (tenant_id, principal_id) REFERENCES mnemion.principals(tenant_id,id)
);
CREATE TABLE mnemion.sign_in_sessions (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    key_id uuid NOT NULL UNIQUE,
    account_version uuid NOT NULL,
    device_name text NOT NULL CHECK (length(device_name) BETWEEN 1 AND 100),
    transport text NOT NULL CHECK (transport IN ('browser','native')),
    access_hash text NOT NULL UNIQUE CHECK (access_hash ~ '^[0-9a-f]{64}$'),
    access_expires_at timestamptz NOT NULL,
    refresh_hash text NOT NULL UNIQUE CHECK (refresh_hash ~ '^[0-9a-f]{64}$'),
    csrf_hash text CHECK (csrf_hash ~ '^[0-9a-f]{64}$'),
    rotations integer NOT NULL DEFAULT 0 CHECK (rotations BETWEEN 0 AND 4096),
    created_at timestamptz NOT NULL DEFAULT now(),
    last_refreshed_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    FOREIGN KEY (tenant_id,key_id,principal_id) REFERENCES mnemion.api_keys(tenant_id,id,principal_id),
    FOREIGN KEY (tenant_id,principal_id) REFERENCES mnemion.password_accounts(tenant_id,principal_id),
    CHECK ((transport='browser') = (csrf_hash IS NOT NULL)),
    CHECK (access_expires_at <= expires_at AND expires_at <= created_at + interval '30 days')
);
CREATE INDEX sign_in_sessions_owner ON mnemion.sign_in_sessions(tenant_id,principal_id);
CREATE INDEX sign_in_sessions_expiry ON mnemion.sign_in_sessions(expires_at,id);
CREATE TABLE mnemion.spent_refresh_tokens (
    token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    session_id uuid NOT NULL REFERENCES mnemion.sign_in_sessions(id) ON DELETE CASCADE
);
CREATE INDEX spent_refresh_session ON mnemion.spent_refresh_tokens(session_id);
CREATE TABLE mnemion.sign_in_invitations (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    issued_by uuid NOT NULL,
    secret_hash text NOT NULL UNIQUE CHECK (secret_hash ~ '^[0-9a-f]{64}$'),
    purpose text NOT NULL CHECK (purpose IN ('enroll','reset')),
    permissions jsonb NOT NULL CHECK (jsonb_typeof(permissions)='object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    revoked_at timestamptz,
    FOREIGN KEY (tenant_id,principal_id) REFERENCES mnemion.principals(tenant_id,id),
    FOREIGN KEY (tenant_id,issued_by) REFERENCES mnemion.principals(tenant_id,id),
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '7 days')
);
CREATE INDEX sign_in_invitations_expiry ON mnemion.sign_in_invitations(expires_at,id);

-- Fixed, bounded retention is independent of a person logging in again. Keep
-- the stable key/audit anchors for historical jobs; remove expired device
-- labels and invitation permission snapshots after the review window.
CREATE FUNCTION mnemion.prune_sign_in_history()
    RETURNS TABLE(spent_tokens integer,sessions integer,invitations integer)
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE instant timestamptz := clock_timestamp();
BEGIN
    spent_tokens := 0; sessions := 0; invitations := 0;
    IF NOT pg_try_advisory_xact_lock(591020146006) THEN RETURN NEXT; RETURN; END IF;
    WITH retired AS (
      SELECT h.token_hash FROM mnemion.spent_refresh_tokens h
      JOIN mnemion.sign_in_sessions s ON s.id=h.session_id
      JOIN mnemion.api_keys k ON k.id=s.key_id AND k.tenant_id=s.tenant_id
      WHERE s.expires_at<=instant OR k.revoked_at IS NOT NULL
      LIMIT 2048 FOR UPDATE OF h SKIP LOCKED
    ) DELETE FROM mnemion.spent_refresh_tokens h USING retired r WHERE h.token_hash=r.token_hash;
    GET DIAGNOSTICS spent_tokens = ROW_COUNT;
    WITH retired AS (
      SELECT s.id FROM mnemion.sign_in_sessions s
      WHERE s.expires_at<=instant-interval '30 days'
        AND NOT EXISTS (SELECT FROM mnemion.spent_refresh_tokens h WHERE h.session_id=s.id)
      ORDER BY s.expires_at,s.id LIMIT 128 FOR UPDATE OF s SKIP LOCKED
    ) DELETE FROM mnemion.sign_in_sessions s USING retired r WHERE s.id=r.id;
    GET DIAGNOSTICS sessions = ROW_COUNT;
    WITH retired AS (
      SELECT i.id FROM mnemion.sign_in_invitations i
      WHERE i.expires_at<=instant-interval '30 days'
      ORDER BY i.expires_at,i.id LIMIT 128 FOR UPDATE OF i SKIP LOCKED
    ) DELETE FROM mnemion.sign_in_invitations i USING retired r WHERE i.id=r.id;
    GET DIAGNOSTICS invitations = ROW_COUNT;
    RETURN NEXT;
END $$;
REVOKE ALL ON FUNCTION mnemion.prune_sign_in_history() FROM PUBLIC,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.prune_sign_in_history() TO mnemion_app;

ALTER TABLE mnemion.password_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE mnemion.sign_in_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE mnemion.spent_refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE mnemion.sign_in_invitations ENABLE ROW LEVEL SECURITY;
-- Verifiers, refresh digests and invitation secrets are only reachable through
-- the narrow authentication functions below, including for administrators.
GRANT SELECT (tenant_id,principal_id,username,reset_required,changed_at)
    ON mnemion.password_accounts TO mnemion_app;
GRANT SELECT (id,tenant_id,principal_id,key_id,device_name,transport,created_at,last_refreshed_at,expires_at)
    ON mnemion.sign_in_sessions TO mnemion_app;
GRANT SELECT (id,tenant_id,principal_id,issued_by,purpose,permissions,created_at,expires_at,consumed_at,revoked_at)
    ON mnemion.sign_in_invitations TO mnemion_app;
CREATE POLICY account_read ON mnemion.password_accounts FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (principal_id=mnemion.principal() OR mnemion.administrator()));
CREATE POLICY session_read ON mnemion.sign_in_sessions FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (principal_id=mnemion.principal() OR mnemion.administrator()));
CREATE POLICY invitation_read ON mnemion.sign_in_invitations FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.administrator());

-- Cross-process throttling counts every attempt before account lookup, including
-- unknown names. Global admission and expiry bound storage; no client IP trust.
CREATE TABLE mnemion.sign_in_attempts (
    subject text PRIMARY KEY CHECK (subject='global' OR subject ~ '^[0-9a-f]{64}$'),
    started_at timestamptz NOT NULL,
    attempts integer NOT NULL CHECK (attempts BETWEEN 0 AND 120)
);
ALTER TABLE mnemion.sign_in_attempts ENABLE ROW LEVEL SECURITY;
CREATE FUNCTION mnemion.admit_sign_in(subject_hash text) RETURNS boolean
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE global_count integer; account_count integer; instant timestamptz := clock_timestamp();
BEGIN
    IF subject_hash IS NULL OR subject_hash !~ '^[0-9a-f]{64}$' THEN RETURN false; END IF;
    PERFORM pg_advisory_xact_lock(591020146005);
    DELETE FROM mnemion.sign_in_attempts WHERE started_at <= instant - interval '10 minutes';
    INSERT INTO mnemion.sign_in_attempts VALUES ('global',instant,1)
      ON CONFLICT (subject) DO UPDATE SET
        started_at=CASE WHEN mnemion.sign_in_attempts.started_at <= instant - interval '1 minute'
          THEN instant ELSE mnemion.sign_in_attempts.started_at END,
        attempts=CASE WHEN mnemion.sign_in_attempts.started_at <= instant - interval '1 minute'
          THEN 1 ELSE least(120,mnemion.sign_in_attempts.attempts+1) END
      RETURNING attempts INTO global_count;
    IF global_count >= 120 THEN RETURN false; END IF;
    IF (SELECT count(*) FROM mnemion.sign_in_attempts) >= 8192 THEN RETURN false; END IF;
    INSERT INTO mnemion.sign_in_attempts VALUES (subject_hash,instant,1)
      ON CONFLICT (subject) DO UPDATE SET attempts=least(120,mnemion.sign_in_attempts.attempts+1)
      RETURNING attempts INTO account_count;
    RETURN account_count <= 10;
END $$;

CREATE FUNCTION mnemion.password_login_lookup(workspace uuid, login_name text)
    RETURNS TABLE(tenant_id uuid, principal_id uuid, password_hash text, account_version uuid)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT a.tenant_id,a.principal_id,a.password_hash,a.version
    FROM mnemion.password_accounts a JOIN mnemion.principals p
      ON p.tenant_id=a.tenant_id AND p.id=a.principal_id
    WHERE a.tenant_id=workspace AND a.username=login_name
      AND NOT a.reset_required AND p.disabled_at IS NULL AND p.kind='human'
$$;

CREATE FUNCTION mnemion.authenticate_session(access_digest text)
    RETURNS TABLE(tenant_id uuid, principal_id uuid, key_id uuid, session_id uuid, expires_at timestamptz)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT s.tenant_id,s.principal_id,s.key_id,s.id,s.access_expires_at
    FROM mnemion.sign_in_sessions s
    JOIN mnemion.api_keys k ON k.tenant_id=s.tenant_id AND k.id=s.key_id AND k.principal_id=s.principal_id
    JOIN mnemion.principals p ON p.tenant_id=s.tenant_id AND p.id=s.principal_id
    JOIN mnemion.password_accounts a ON a.tenant_id=s.tenant_id AND a.principal_id=s.principal_id
    WHERE s.access_hash=access_digest AND s.access_expires_at > clock_timestamp()
      AND s.expires_at > clock_timestamp() AND k.revoked_at IS NULL AND k.session_key
      AND k.expires_at > clock_timestamp() AND p.disabled_at IS NULL
      AND NOT a.reset_required AND a.version=s.account_version
$$;

REVOKE ALL ON FUNCTION mnemion.admit_sign_in(text),
    mnemion.password_login_lookup(uuid,text), mnemion.authenticate_session(text)
    FROM PUBLIC,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.admit_sign_in(text),
    mnemion.password_login_lookup(uuid,text), mnemion.authenticate_session(text)
    TO mnemion_app;

CREATE FUNCTION mnemion._sign_in_lock(workspace uuid) RETURNS void
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT pg_advisory_xact_lock(hashtextextended('administrator-access:' || workspace::text,0))
$$;
CREATE FUNCTION mnemion._sign_in_audit(workspace uuid,person uuid,event text,resource uuid)
    RETURNS void LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
    INSERT INTO mnemion.audit_events(tenant_id,id,principal_id,action,resource_id,details)
      VALUES(workspace,gen_random_uuid(),person,event,resource::text,'{}'::jsonb)
$$;
CREATE FUNCTION mnemion._revoke_password_sessions(workspace uuid,person uuid) RETURNS void
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE mnemion.api_keys k SET revoked_at=coalesce(k.revoked_at,clock_timestamp())
      WHERE k.tenant_id=workspace AND k.principal_id=person AND k.session_key
$$;

CREATE FUNCTION mnemion.set_password_account(login_name text,verifier text,expected_verifier text)
    RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE previous mnemion.password_accounts%ROWTYPE;
BEGIN
    PERFORM mnemion._sign_in_lock(mnemion.tenant());
    IF NOT EXISTS (SELECT FROM mnemion.principals WHERE tenant_id=mnemion.tenant()
        AND id=mnemion.principal() AND disabled_at IS NULL AND kind='human') THEN RETURN false; END IF;
    SELECT * INTO previous FROM mnemion.password_accounts
      WHERE tenant_id=mnemion.tenant() AND principal_id=mnemion.principal() FOR UPDATE;
    IF FOUND AND (previous.reset_required OR expected_verifier IS NULL
      OR previous.password_hash<>expected_verifier) THEN RETURN false; END IF;
    IF NOT FOUND AND expected_verifier IS NOT NULL THEN RETURN false; END IF;
    INSERT INTO mnemion.password_accounts(tenant_id,principal_id,username,password_hash,version)
      VALUES(mnemion.tenant(),mnemion.principal(),login_name,verifier,gen_random_uuid())
      ON CONFLICT(tenant_id,principal_id) DO UPDATE SET username=excluded.username,
        password_hash=excluded.password_hash,version=excluded.version,changed_at=clock_timestamp();
    PERFORM mnemion._revoke_password_sessions(mnemion.tenant(),mnemion.principal());
    UPDATE mnemion.sign_in_invitations SET revoked_at=coalesce(revoked_at,clock_timestamp())
      WHERE tenant_id=mnemion.tenant() AND principal_id=mnemion.principal() AND consumed_at IS NULL;
    PERFORM mnemion._sign_in_audit(mnemion.tenant(),mnemion.principal(),'password.changed',mnemion.principal());
    RETURN true;
END $$;

CREATE FUNCTION mnemion.issue_password_session(
    workspace uuid,person uuid,expected_verifier text,expected_version uuid,
    session_uuid uuid,key_uuid uuid,anchor_hash text,access_digest text,refresh_digest text,
    csrf_digest text,label text,channel text
) RETURNS SETOF mnemion.sign_in_sessions
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE instant timestamptz;
BEGIN
    PERFORM mnemion._sign_in_lock(workspace);
    instant := clock_timestamp();
    IF NOT EXISTS (SELECT FROM mnemion.password_accounts a JOIN mnemion.principals p
      ON p.tenant_id=a.tenant_id AND p.id=a.principal_id
      WHERE a.tenant_id=workspace AND a.principal_id=person AND a.password_hash=expected_verifier
        AND a.version=expected_version AND NOT a.reset_required AND p.disabled_at IS NULL
        AND p.kind='human') THEN RETURN; END IF;
    -- Retain at most the live session's bounded rotation history.
    DELETE FROM mnemion.spent_refresh_tokens h USING mnemion.sign_in_sessions s,mnemion.api_keys k
      WHERE h.session_id=s.id AND s.tenant_id=workspace AND s.principal_id=person
        AND k.tenant_id=s.tenant_id AND k.id=s.key_id
        AND (s.expires_at<=instant OR k.revoked_at IS NOT NULL);
    IF (SELECT count(*) FROM mnemion.sign_in_sessions s JOIN mnemion.api_keys k
      ON k.tenant_id=s.tenant_id AND k.id=s.key_id
      WHERE s.tenant_id=workspace AND s.principal_id=person AND s.expires_at>instant
        AND k.revoked_at IS NULL) >= 32 THEN RETURN; END IF;
    INSERT INTO mnemion.api_keys(tenant_id,id,principal_id,name,token_hash,prefix,expires_at,session_key)
      VALUES(workspace,key_uuid,person,'Device session',anchor_hash,'session',instant+interval '30 days',true);
    INSERT INTO mnemion.sign_in_sessions(id,tenant_id,principal_id,key_id,account_version,device_name,
      transport,access_hash,access_expires_at,refresh_hash,csrf_hash,created_at,last_refreshed_at,expires_at)
      VALUES(session_uuid,workspace,person,key_uuid,expected_version,label,channel,access_digest,
        instant+interval '15 minutes',refresh_digest,csrf_digest,instant,instant,instant+interval '30 days');
    PERFORM mnemion._sign_in_audit(workspace,person,'session.created',session_uuid);
    RETURN QUERY SELECT * FROM mnemion.sign_in_sessions WHERE id=session_uuid;
END $$;

CREATE FUNCTION mnemion.rotate_password_session(
    previous_refresh text,access_digest text,refresh_digest text,csrf_digest text,channel text,workspace uuid,expected_session uuid
) RETURNS TABLE(result text,session_id uuid,tenant_id uuid,principal_id uuid,key_id uuid,
    access_expires_at timestamptz,expires_at timestamptz,rotation integer)
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE current_session mnemion.sign_in_sessions%ROWTYPE; instant timestamptz; reused boolean;
BEGIN
    SELECT s.* INTO current_session FROM mnemion.sign_in_sessions s
      WHERE s.refresh_hash=previous_refresh OR s.id=(
        SELECT h.session_id FROM mnemion.spent_refresh_tokens h WHERE h.token_hash=previous_refresh);
    IF NOT FOUND THEN RETURN QUERY SELECT 'invalid',NULL::uuid,NULL::uuid,NULL::uuid,NULL::uuid,NULL::timestamptz,NULL::timestamptz,NULL::integer; RETURN; END IF;
    PERFORM mnemion._sign_in_lock(current_session.tenant_id);
    SELECT s.* INTO current_session FROM mnemion.sign_in_sessions s
      WHERE s.id=current_session.id FOR UPDATE;
    instant := clock_timestamp();
    IF (workspace IS NOT NULL AND current_session.tenant_id<>workspace)
      OR (expected_session IS NOT NULL AND current_session.id<>expected_session)
      OR current_session.transport<>channel OR current_session.csrf_hash IS DISTINCT FROM csrf_digest
      OR current_session.expires_at<=instant OR NOT EXISTS (
        SELECT FROM mnemion.api_keys k JOIN mnemion.principals p
          ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
        JOIN mnemion.password_accounts a ON a.tenant_id=p.tenant_id AND a.principal_id=p.id
        WHERE k.id=current_session.key_id AND k.tenant_id=current_session.tenant_id
          AND k.session_key AND k.revoked_at IS NULL AND k.expires_at>instant
          AND p.disabled_at IS NULL AND NOT a.reset_required AND a.version=current_session.account_version
      ) THEN RETURN QUERY SELECT 'invalid',NULL::uuid,NULL::uuid,NULL::uuid,NULL::uuid,NULL::timestamptz,NULL::timestamptz,NULL::integer; RETURN; END IF;
    reused := current_session.refresh_hash<>previous_refresh;
    IF reused AND NOT EXISTS (SELECT FROM mnemion.spent_refresh_tokens h
      WHERE h.session_id=current_session.id AND h.token_hash=previous_refresh) THEN
      RETURN QUERY SELECT 'invalid',NULL::uuid,NULL::uuid,NULL::uuid,NULL::uuid,NULL::timestamptz,NULL::timestamptz,NULL::integer; RETURN;
    END IF;
    IF reused OR current_session.rotations>=4096 THEN
      UPDATE mnemion.api_keys k SET revoked_at=instant
        WHERE k.tenant_id=current_session.tenant_id AND k.id=current_session.key_id;
      PERFORM mnemion._sign_in_audit(current_session.tenant_id,current_session.principal_id,
        CASE WHEN reused THEN 'session.refresh_reused' ELSE 'session.refresh_limit' END,current_session.id);
      -- The caller commits this revocation before returning an HTTP error.
      RETURN QUERY SELECT 'revoked',NULL::uuid,NULL::uuid,NULL::uuid,NULL::uuid,NULL::timestamptz,NULL::timestamptz,NULL::integer; RETURN;
    END IF;
    INSERT INTO mnemion.spent_refresh_tokens(token_hash,session_id)
      VALUES(previous_refresh,current_session.id);
    UPDATE mnemion.sign_in_sessions s SET access_hash=access_digest,
      access_expires_at=least(instant+interval '15 minutes',s.expires_at),
      refresh_hash=refresh_digest,rotations=s.rotations+1,last_refreshed_at=instant
      WHERE s.id=current_session.id;
    RETURN QUERY SELECT 'ok',s.id,s.tenant_id,s.principal_id,s.key_id,s.access_expires_at,s.expires_at,s.rotations
      FROM mnemion.sign_in_sessions s WHERE s.id=current_session.id;
END $$;

CREATE FUNCTION mnemion.revoke_password_session(session_uuid uuid) RETURNS boolean
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE changed uuid;
BEGIN
    PERFORM mnemion._sign_in_lock(mnemion.tenant());
    UPDATE mnemion.api_keys k SET revoked_at=coalesce(k.revoked_at,clock_timestamp())
      FROM mnemion.sign_in_sessions s
      WHERE s.id=session_uuid AND s.tenant_id=mnemion.tenant()
        AND (s.principal_id=mnemion.principal() OR mnemion.administrator())
        AND k.tenant_id=s.tenant_id AND k.id=s.key_id RETURNING s.id INTO changed;
    IF changed IS NULL THEN RETURN false; END IF;
    PERFORM mnemion._sign_in_audit(mnemion.tenant(),mnemion.principal(),'session.revoked',session_uuid);
    RETURN true;
END $$;

REVOKE ALL ON FUNCTION mnemion._sign_in_lock(uuid),mnemion._sign_in_audit(uuid,uuid,text,uuid),
    mnemion._revoke_password_sessions(uuid,uuid),mnemion.set_password_account(text,text,text),
    mnemion.issue_password_session(uuid,uuid,text,uuid,uuid,uuid,text,text,text,text,text,text),
    mnemion.rotate_password_session(text,text,text,text,text,uuid,uuid),mnemion.revoke_password_session(uuid)
    FROM PUBLIC,mnemion_app,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.set_password_account(text,text,text),
    mnemion.issue_password_session(uuid,uuid,text,uuid,uuid,uuid,text,text,text,text,text,text),
    mnemion.rotate_password_session(text,text,text,text,text,uuid,uuid),mnemion.revoke_password_session(uuid)
    TO mnemion_app;

CREATE FUNCTION mnemion._invitation_permissions(workspace uuid,person uuid) RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('administrator',p.administrator,'spaces',coalesce((
      SELECT jsonb_agg(jsonb_build_object('space_id',g.space_id,'role',g.role) ORDER BY g.space_id)
      FROM mnemion.space_grants g WHERE g.tenant_id=workspace AND g.principal_id=person
    ),'[]'::jsonb)) FROM mnemion.principals p
      WHERE p.tenant_id=workspace AND p.id=person AND p.disabled_at IS NULL AND p.kind='human'
$$;

CREATE FUNCTION mnemion.create_sign_in_invitation(person uuid,intent text,secret_digest text,seconds integer)
    RETURNS TABLE(id uuid,expires_at timestamptz,purpose text)
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE scope jsonb; invitation uuid := gen_random_uuid(); instant timestamptz;
BEGIN
    PERFORM mnemion._sign_in_lock(mnemion.tenant());
    IF NOT mnemion.administrator() OR intent NOT IN ('enroll','reset')
      OR seconds NOT BETWEEN 60 AND 604800 THEN RETURN; END IF;
    scope := mnemion._invitation_permissions(mnemion.tenant(),person);
    IF scope IS NULL THEN RETURN; END IF;
    IF (intent='reset') <> EXISTS (SELECT FROM mnemion.password_accounts a
      WHERE a.tenant_id=mnemion.tenant() AND a.principal_id=person) THEN RETURN; END IF;
    instant := clock_timestamp();
    UPDATE mnemion.sign_in_invitations i SET revoked_at=coalesce(i.revoked_at,instant)
      WHERE i.tenant_id=mnemion.tenant() AND i.principal_id=person AND i.consumed_at IS NULL;
    IF intent='reset' THEN
      UPDATE mnemion.password_accounts a SET reset_required=true,version=gen_random_uuid()
        WHERE a.tenant_id=mnemion.tenant() AND a.principal_id=person;
      PERFORM mnemion._revoke_password_sessions(mnemion.tenant(),person);
    END IF;
    INSERT INTO mnemion.sign_in_invitations(id,tenant_id,principal_id,issued_by,secret_hash,
      purpose,permissions,created_at,expires_at)
      VALUES(invitation,mnemion.tenant(),person,mnemion.principal(),secret_digest,intent,scope,
        instant,instant+make_interval(secs=>seconds));
    PERFORM mnemion._sign_in_audit(mnemion.tenant(),mnemion.principal(),'invitation.created',invitation);
    RETURN QUERY SELECT i.id,i.expires_at,i.purpose FROM mnemion.sign_in_invitations i WHERE i.id=invitation;
END $$;

CREATE FUNCTION mnemion.preview_sign_in_invitation(secret_digest text) RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('id',i.id,'workspace_id',t.id,'workspace_name',t.name,
      'principal_id',p.id,'person_name',p.name,'administrator',p.administrator,
      'purpose',i.purpose,'expires_at',i.expires_at,'suggested_login',a.username,'spaces',coalesce((
        SELECT jsonb_agg(jsonb_build_object('space_id',g.space_id,'name',s.name,'role',g.role) ORDER BY g.space_id)
        FROM mnemion.space_grants g JOIN mnemion.spaces s ON s.tenant_id=g.tenant_id AND s.id=g.space_id
        WHERE g.tenant_id=i.tenant_id AND g.principal_id=i.principal_id
      ),'[]'::jsonb))
    FROM mnemion.sign_in_invitations i
    JOIN mnemion.tenants t ON t.id=i.tenant_id
    JOIN mnemion.principals p ON p.tenant_id=i.tenant_id AND p.id=i.principal_id
    JOIN mnemion.principals issuer ON issuer.tenant_id=i.tenant_id AND issuer.id=i.issued_by
    LEFT JOIN mnemion.password_accounts a ON a.tenant_id=i.tenant_id AND a.principal_id=i.principal_id
    WHERE i.secret_hash=secret_digest AND i.revoked_at IS NULL AND i.consumed_at IS NULL
      AND i.expires_at>clock_timestamp() AND issuer.administrator AND issuer.disabled_at IS NULL
      AND p.disabled_at IS NULL AND p.kind='human'
      AND i.permissions=mnemion._invitation_permissions(i.tenant_id,i.principal_id)
      AND ((i.purpose='enroll' AND a.principal_id IS NULL) OR (i.purpose='reset' AND a.reset_required))
$$;

CREATE FUNCTION mnemion.accept_sign_in_invitation(secret_digest text,login_name text,verifier text)
    RETURNS TABLE(tenant_id uuid,principal_id uuid,password_hash text,account_version uuid)
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE invite mnemion.sign_in_invitations%ROWTYPE; preview jsonb;
BEGIN
    SELECT i.* INTO invite FROM mnemion.sign_in_invitations i WHERE i.secret_hash=secret_digest;
    IF NOT FOUND THEN RETURN; END IF;
    PERFORM mnemion._sign_in_lock(invite.tenant_id);
    SELECT i.* INTO invite FROM mnemion.sign_in_invitations i WHERE i.id=invite.id FOR UPDATE;
    preview := mnemion.preview_sign_in_invitation(secret_digest);
    IF preview IS NULL THEN RETURN; END IF;
    INSERT INTO mnemion.password_accounts AS account(tenant_id,principal_id,username,password_hash,version)
      VALUES(invite.tenant_id,invite.principal_id,login_name,verifier,gen_random_uuid())
      ON CONFLICT ON CONSTRAINT password_accounts_pkey DO UPDATE SET username=excluded.username,
        password_hash=excluded.password_hash,version=excluded.version,reset_required=false,changed_at=clock_timestamp();
    PERFORM mnemion._revoke_password_sessions(invite.tenant_id,invite.principal_id);
    UPDATE mnemion.sign_in_invitations i SET consumed_at=clock_timestamp() WHERE i.id=invite.id;
    UPDATE mnemion.sign_in_invitations i SET revoked_at=coalesce(i.revoked_at,clock_timestamp())
      WHERE i.tenant_id=invite.tenant_id AND i.principal_id=invite.principal_id AND i.id<>invite.id AND i.consumed_at IS NULL;
    PERFORM mnemion._sign_in_audit(invite.tenant_id,invite.principal_id,'invitation.accepted',invite.id);
    RETURN QUERY SELECT a.tenant_id,a.principal_id,a.password_hash,a.version
      FROM mnemion.password_accounts a WHERE a.tenant_id=invite.tenant_id AND a.principal_id=invite.principal_id;
END $$;

CREATE FUNCTION mnemion.revoke_sign_in_invitation(invitation_uuid uuid) RETURNS boolean
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE changed uuid;
BEGIN
    PERFORM mnemion._sign_in_lock(mnemion.tenant());
    IF NOT mnemion.administrator() THEN RETURN false; END IF;
    UPDATE mnemion.sign_in_invitations i SET revoked_at=coalesce(i.revoked_at,clock_timestamp())
      WHERE i.id=invitation_uuid AND i.tenant_id=mnemion.tenant() RETURNING i.id INTO changed;
    IF changed IS NULL THEN RETURN false; END IF;
    PERFORM mnemion._sign_in_audit(mnemion.tenant(),mnemion.principal(),'invitation.revoked',invitation_uuid);
    RETURN true;
END $$;

REVOKE ALL ON FUNCTION mnemion._invitation_permissions(uuid,uuid),
    mnemion.create_sign_in_invitation(uuid,text,text,integer),mnemion.preview_sign_in_invitation(text),
    mnemion.accept_sign_in_invitation(text,text,text),mnemion.revoke_sign_in_invitation(uuid)
    FROM PUBLIC,mnemion_app,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.create_sign_in_invitation(uuid,text,text,integer),
    mnemion.preview_sign_in_invitation(text),mnemion.accept_sign_in_invitation(text,text,text),
    mnemion.revoke_sign_in_invitation(uuid) TO mnemion_app;

CREATE FUNCTION mnemion.sign_out_password_session(refresh_digest text,csrf_digest text,channel text,workspace uuid,expected_session uuid)
    RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE device mnemion.sign_in_sessions%ROWTYPE;
BEGIN
    PERFORM mnemion._sign_in_lock(workspace);
    SELECT s.* INTO device FROM mnemion.sign_in_sessions s WHERE s.tenant_id=workspace
      AND (expected_session IS NULL OR s.id=expected_session)
      AND s.transport=channel AND s.csrf_hash IS NOT DISTINCT FROM csrf_digest
      AND (s.refresh_hash=refresh_digest OR s.id=(SELECT h.session_id
        FROM mnemion.spent_refresh_tokens h WHERE h.token_hash=refresh_digest)) FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    UPDATE mnemion.api_keys k SET revoked_at=clock_timestamp()
      WHERE k.tenant_id=device.tenant_id AND k.id=device.key_id AND k.revoked_at IS NULL;
    IF FOUND THEN PERFORM mnemion._sign_in_audit(device.tenant_id,device.principal_id,'session.signed_out',device.id); END IF;
    RETURN true;
END $$;
REVOKE ALL ON FUNCTION mnemion.sign_out_password_session(text,text,text,uuid,uuid) FROM PUBLIC,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.sign_out_password_session(text,text,text,uuid,uuid) TO mnemion_app;
