-- Company identities prove who is signing in; existing principals/grants still
-- decide their access. Provider configuration belongs to the host operator.
CREATE TABLE mnemion.company_links (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    provider_id text NOT NULL CHECK (provider_id ~ '^[a-z][a-z0-9-]{0,63}$'),
    issuer text NOT NULL CHECK (length(issuer) BETWEEN 1 AND 2048),
    client_id text NOT NULL CHECK (length(client_id) BETWEEN 1 AND 512),
    subject text NOT NULL CHECK (length(subject) BETWEEN 1 AND 255),
    identity_hash text NOT NULL CHECK (identity_hash ~ '^[0-9a-f]{64}$'),
    policy_hash text NOT NULL CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
    version uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    changed_at timestamptz NOT NULL DEFAULT now(),
    last_authenticated_at timestamptz,
    revoked_at timestamptz,
    UNIQUE (tenant_id,identity_hash),
    UNIQUE (tenant_id,principal_id,id),
    FOREIGN KEY (tenant_id,principal_id) REFERENCES mnemion.principals(tenant_id,id)
);
ALTER TABLE mnemion.company_links ENABLE ROW LEVEL SECURITY;
GRANT SELECT (id,tenant_id,principal_id,provider_id,issuer,client_id,subject,created_at,changed_at,last_authenticated_at,revoked_at)
    ON mnemion.company_links TO mnemion_app;
CREATE POLICY company_link_read ON mnemion.company_links FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (principal_id=mnemion.principal() OR mnemion.administrator()));

-- Preserve existing password sessions. Company sessions need no synthetic
-- password account and cannot authenticate through the password-only verifier.
ALTER TABLE mnemion.sign_in_sessions DROP CONSTRAINT sign_in_sessions_tenant_id_principal_id_fkey;
ALTER TABLE mnemion.sign_in_sessions ADD COLUMN company_link_id uuid;
ALTER TABLE mnemion.sign_in_sessions ADD FOREIGN KEY (tenant_id,principal_id,company_link_id)
    REFERENCES mnemion.company_links(tenant_id,principal_id,id);
GRANT SELECT (company_link_id) ON mnemion.sign_in_sessions TO mnemion_app;
CREATE INDEX company_link_sessions ON mnemion.sign_in_sessions(company_link_id) WHERE company_link_id IS NOT NULL;

CREATE TABLE mnemion.company_login_requests (
    state_hash text PRIMARY KEY CHECK (state_hash ~ '^[0-9a-f]{64}$'),
    proof_hash text NOT NULL CHECK (proof_hash ~ '^[0-9a-f]{64}$'),
    tenant_id uuid NOT NULL REFERENCES mnemion.tenants(id),
    provider_id text NOT NULL CHECK (provider_id ~ '^[a-z][a-z0-9-]{0,63}$'),
    policy_hash text NOT NULL CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object' AND octet_length(payload::text)<=4096),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now()+interval '5 minutes',
    claimed_at timestamptz,
    completed_at timestamptz
);
ALTER TABLE mnemion.company_login_requests ENABLE ROW LEVEL SECURITY;
CREATE INDEX company_login_expiry ON mnemion.company_login_requests(expires_at);

CREATE FUNCTION mnemion.create_company_login(state_digest text,proof_digest text,workspace uuid,
    provider text,policy text,body jsonb) RETURNS boolean
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(591020146009);
    DELETE FROM mnemion.company_login_requests WHERE expires_at<=clock_timestamp();
    IF (SELECT count(*) FROM mnemion.company_login_requests)>=1024
      OR NOT EXISTS (SELECT FROM mnemion.tenants WHERE id=workspace) THEN RETURN false; END IF;
    INSERT INTO mnemion.company_login_requests(state_hash,proof_hash,tenant_id,provider_id,policy_hash,payload)
      VALUES(state_digest,proof_digest,workspace,provider,policy,body);
    RETURN true;
END $$;

CREATE FUNCTION mnemion.company_login_callback(state_digest text) RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('workspace_id',tenant_id,'provider_id',provider_id,'policy_hash',policy_hash,
      'transport',payload->>'transport','callback_uri',payload->>'callback_uri')
    FROM mnemion.company_login_requests WHERE state_hash=state_digest
      AND expires_at>clock_timestamp() AND claimed_at IS NULL
$$;

CREATE FUNCTION mnemion.claim_company_login(state_digest text,proof_digest text) RETURNS jsonb
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE mnemion.company_login_requests SET claimed_at=clock_timestamp()
      WHERE state_hash=state_digest AND proof_hash=proof_digest
        AND expires_at>clock_timestamp() AND claimed_at IS NULL
    RETURNING payload || jsonb_build_object('workspace_id',tenant_id,'provider_id',provider_id,'policy_hash',policy_hash)
$$;

CREATE FUNCTION mnemion._link_company_identity(workspace uuid,person uuid,provider text,
    issuer_url text,client text,external_subject text,external_hash text,policy text)
    RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE previous mnemion.company_links%ROWTYPE; linked uuid := gen_random_uuid();
BEGIN
    IF NOT EXISTS (SELECT FROM mnemion.principals WHERE tenant_id=workspace AND id=person
      AND kind='human' AND disabled_at IS NULL) THEN RETURN NULL; END IF;
    SELECT * INTO previous FROM mnemion.company_links
      WHERE tenant_id=workspace AND identity_hash=external_hash FOR UPDATE;
    IF FOUND THEN
      -- Identity associations survive revocation and cannot be reassigned.
      IF previous.principal_id<>person OR previous.issuer<>issuer_url OR previous.client_id<>client
        OR previous.subject<>external_subject THEN RETURN NULL; END IF;
      linked := previous.id;
      IF previous.revoked_at IS NOT NULL OR previous.policy_hash<>policy OR previous.provider_id<>provider THEN
        UPDATE mnemion.api_keys k SET revoked_at=coalesce(k.revoked_at,clock_timestamp())
          FROM mnemion.sign_in_sessions s WHERE s.company_link_id=linked AND k.id=s.key_id AND k.tenant_id=s.tenant_id;
        UPDATE mnemion.company_links SET revoked_at=NULL,version=gen_random_uuid(),policy_hash=policy,
          provider_id=provider,changed_at=clock_timestamp() WHERE id=linked;
      END IF;
    ELSE
      INSERT INTO mnemion.company_links(id,tenant_id,principal_id,provider_id,issuer,client_id,subject,identity_hash,policy_hash,version)
        VALUES(linked,workspace,person,provider,issuer_url,client,external_subject,external_hash,policy,gen_random_uuid());
    END IF;
    RETURN linked;
END $$;

CREATE FUNCTION mnemion.link_company_identity(person uuid,provider text,issuer_url text,client text,
    external_subject text,external_hash text,policy text) RETURNS uuid
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE linked uuid;
BEGIN
    PERFORM mnemion._sign_in_lock(mnemion.tenant());
    IF NOT mnemion.administrator() THEN RETURN NULL; END IF;
    linked := mnemion._link_company_identity(mnemion.tenant(),person,provider,issuer_url,client,external_subject,external_hash,policy);
    IF linked IS NOT NULL THEN
      PERFORM mnemion._sign_in_audit(mnemion.tenant(),mnemion.principal(),'company.linked',linked);
    END IF;
    RETURN linked;
END $$;

CREATE FUNCTION mnemion.revoke_company_identity(link_uuid uuid) RETURNS boolean
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE changed uuid;
BEGIN
    PERFORM mnemion._sign_in_lock(mnemion.tenant());
    UPDATE mnemion.company_links SET revoked_at=coalesce(revoked_at,clock_timestamp()),
      changed_at=clock_timestamp() WHERE id=link_uuid AND tenant_id=mnemion.tenant()
        AND (principal_id=mnemion.principal() OR mnemion.administrator()) RETURNING id INTO changed;
    IF changed IS NULL THEN RETURN false; END IF;
    UPDATE mnemion.api_keys k SET revoked_at=coalesce(k.revoked_at,clock_timestamp())
      FROM mnemion.sign_in_sessions s WHERE s.company_link_id=changed AND k.id=s.key_id AND k.tenant_id=s.tenant_id;
    PERFORM mnemion._sign_in_audit(mnemion.tenant(),mnemion.principal(),'company.revoked',changed);
    RETURN true;
END $$;

CREATE FUNCTION mnemion.issue_company_session(state_digest text,proof_digest text,issuer_url text,
    client text,external_subject text,external_hash text,seconds integer,session_uuid uuid,key_uuid uuid,
    anchor_hash text,access_digest text,refresh_digest text,csrf_digest text)
    RETURNS SETOF mnemion.sign_in_sessions
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE request mnemion.company_login_requests%ROWTYPE; linked mnemion.company_links%ROWTYPE;
    invite mnemion.sign_in_invitations%ROWTYPE; link_uuid uuid; instant timestamptz;
BEGIN
    SELECT * INTO request FROM mnemion.company_login_requests WHERE state_hash=state_digest
      AND proof_hash=proof_digest AND claimed_at IS NOT NULL AND completed_at IS NULL
      AND expires_at>clock_timestamp() FOR UPDATE;
    IF NOT FOUND OR seconds NOT BETWEEN 900 AND 86400 THEN RETURN; END IF;
    PERFORM mnemion._sign_in_lock(request.tenant_id);
    instant := clock_timestamp();
    IF request.payload->>'invitation_hash' IS NOT NULL THEN
      SELECT * INTO invite FROM mnemion.sign_in_invitations
        WHERE secret_hash=request.payload->>'invitation_hash' AND tenant_id=request.tenant_id FOR UPDATE;
      IF NOT FOUND OR invite.purpose<>'enroll'
        OR mnemion.preview_sign_in_invitation(invite.secret_hash) IS NULL THEN RETURN; END IF;
      link_uuid := mnemion._link_company_identity(request.tenant_id,invite.principal_id,request.provider_id,
        issuer_url,client,external_subject,external_hash,request.policy_hash);
      IF link_uuid IS NULL THEN RETURN; END IF;
      UPDATE mnemion.sign_in_invitations SET consumed_at=instant WHERE id=invite.id;
      UPDATE mnemion.sign_in_invitations SET revoked_at=coalesce(revoked_at,instant)
        WHERE tenant_id=invite.tenant_id AND principal_id=invite.principal_id AND id<>invite.id AND consumed_at IS NULL;
      PERFORM mnemion._sign_in_audit(request.tenant_id,invite.principal_id,'company.invitation_accepted',invite.id);
    END IF;
    SELECT * INTO linked FROM mnemion.company_links WHERE tenant_id=request.tenant_id
      AND identity_hash=external_hash AND provider_id=request.provider_id AND policy_hash=request.policy_hash
      AND issuer=issuer_url AND client_id=client AND subject=external_subject AND revoked_at IS NULL;
    IF NOT FOUND OR NOT EXISTS (SELECT FROM mnemion.principals WHERE tenant_id=linked.tenant_id
      AND id=linked.principal_id AND kind='human' AND disabled_at IS NULL) THEN RETURN; END IF;
    IF (SELECT count(*) FROM mnemion.sign_in_sessions s JOIN mnemion.api_keys k
      ON k.tenant_id=s.tenant_id AND k.id=s.key_id WHERE s.tenant_id=linked.tenant_id
      AND s.principal_id=linked.principal_id AND s.expires_at>instant AND k.revoked_at IS NULL)>=32 THEN RETURN; END IF;
    INSERT INTO mnemion.api_keys(tenant_id,id,principal_id,name,token_hash,prefix,expires_at,session_key)
      VALUES(linked.tenant_id,key_uuid,linked.principal_id,'Company device session',anchor_hash,'session',instant+make_interval(secs=>seconds),true);
    INSERT INTO mnemion.sign_in_sessions(id,tenant_id,principal_id,key_id,account_version,device_name,
      transport,access_hash,access_expires_at,refresh_hash,csrf_hash,created_at,last_refreshed_at,expires_at,company_link_id)
      VALUES(session_uuid,linked.tenant_id,linked.principal_id,key_uuid,linked.version,request.payload->>'device_name',
        request.payload->>'transport',access_digest,instant+interval '15 minutes',refresh_digest,csrf_digest,
        instant,instant,instant+make_interval(secs=>seconds),linked.id);
    UPDATE mnemion.company_login_requests SET completed_at=instant WHERE state_hash=state_digest;
    UPDATE mnemion.company_links SET last_authenticated_at=instant WHERE id=linked.id;
    PERFORM mnemion._sign_in_audit(linked.tenant_id,linked.principal_id,'company.session_created',session_uuid);
    RETURN QUERY SELECT * FROM mnemion.sign_in_sessions WHERE id=session_uuid;
END $$;

CREATE OR REPLACE FUNCTION mnemion.authenticate_session(access_digest text)
    RETURNS TABLE(tenant_id uuid, principal_id uuid, key_id uuid, session_id uuid, expires_at timestamptz)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT s.tenant_id,s.principal_id,s.key_id,s.id,s.access_expires_at
    FROM mnemion.sign_in_sessions s
    JOIN mnemion.api_keys k ON k.tenant_id=s.tenant_id AND k.id=s.key_id AND k.principal_id=s.principal_id
    JOIN mnemion.principals p ON p.tenant_id=s.tenant_id AND p.id=s.principal_id
    JOIN mnemion.password_accounts a ON a.tenant_id=s.tenant_id AND a.principal_id=s.principal_id
    WHERE s.access_hash=access_digest AND s.company_link_id IS NULL AND s.access_expires_at>clock_timestamp()
      AND s.expires_at>clock_timestamp() AND k.revoked_at IS NULL AND k.session_key
      AND k.expires_at>clock_timestamp() AND p.disabled_at IS NULL
      AND NOT a.reset_required AND a.version=s.account_version
$$;

CREATE FUNCTION mnemion.authenticate_company_session(access_digest text,policies text[])
    RETURNS TABLE(tenant_id uuid,principal_id uuid,key_id uuid,session_id uuid,expires_at timestamptz)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT s.tenant_id,s.principal_id,s.key_id,s.id,s.access_expires_at
    FROM mnemion.sign_in_sessions s
    JOIN mnemion.api_keys k ON k.tenant_id=s.tenant_id AND k.id=s.key_id AND k.principal_id=s.principal_id
    JOIN mnemion.principals p ON p.tenant_id=s.tenant_id AND p.id=s.principal_id
    JOIN mnemion.company_links l ON l.tenant_id=s.tenant_id AND l.id=s.company_link_id AND l.principal_id=s.principal_id
    WHERE s.access_hash=access_digest AND s.access_expires_at>clock_timestamp() AND s.expires_at>clock_timestamp()
      AND k.revoked_at IS NULL AND k.session_key AND k.expires_at>clock_timestamp() AND p.disabled_at IS NULL
      AND l.revoked_at IS NULL AND l.version=s.account_version AND l.policy_hash=ANY(policies)
$$;

REVOKE ALL ON FUNCTION mnemion._link_company_identity(uuid,uuid,text,text,text,text,text,text)
    FROM PUBLIC,mnemion_app,mnemion_worker;
REVOKE ALL ON FUNCTION mnemion.create_company_login(text,text,uuid,text,text,jsonb),
    mnemion.company_login_callback(text),mnemion.claim_company_login(text,text),
    mnemion.link_company_identity(uuid,text,text,text,text,text,text),mnemion.revoke_company_identity(uuid),
    mnemion.issue_company_session(text,text,text,text,text,text,integer,uuid,uuid,text,text,text,text),
    mnemion.authenticate_company_session(text,text[]) FROM PUBLIC,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.create_company_login(text,text,uuid,text,text,jsonb),
    mnemion.company_login_callback(text),mnemion.claim_company_login(text,text),
    mnemion.link_company_identity(uuid,text,text,text,text,text,text),mnemion.revoke_company_identity(uuid),
    mnemion.issue_company_session(text,text,text,text,text,text,integer,uuid,uuid,text,text,text,text),
    mnemion.authenticate_company_session(text,text[]) TO mnemion_app;

-- Refresh rotation retains its existing atomic reuse/CSRF/identity checks.
CREATE OR REPLACE FUNCTION mnemion.rotate_password_session(
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
      OR current_session.company_link_id IS NOT NULL
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

CREATE FUNCTION mnemion.rotate_device_session(
    previous_refresh text,access_digest text,refresh_digest text,csrf_digest text,channel text,workspace uuid,expected_session uuid,policies text[]
) RETURNS TABLE(result text,session_id uuid,tenant_id uuid,principal_id uuid,key_id uuid,
    access_expires_at timestamptz,expires_at timestamptz,rotation integer,authentication text)
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE current_session mnemion.sign_in_sessions%ROWTYPE; instant timestamptz; reused boolean;
BEGIN
    SELECT s.* INTO current_session FROM mnemion.sign_in_sessions s
      WHERE s.refresh_hash=previous_refresh OR s.id=(
        SELECT h.session_id FROM mnemion.spent_refresh_tokens h WHERE h.token_hash=previous_refresh);
    IF NOT FOUND THEN RETURN QUERY SELECT 'invalid',NULL::uuid,NULL::uuid,NULL::uuid,NULL::uuid,NULL::timestamptz,NULL::timestamptz,NULL::integer,NULL::text; RETURN; END IF;
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
        LEFT JOIN mnemion.password_accounts a ON a.tenant_id=p.tenant_id AND a.principal_id=p.id
        LEFT JOIN mnemion.company_links l ON l.tenant_id=p.tenant_id AND l.principal_id=p.id AND l.id=current_session.company_link_id
        WHERE k.id=current_session.key_id AND k.tenant_id=current_session.tenant_id
          AND k.session_key AND k.revoked_at IS NULL AND k.expires_at>instant
          AND p.disabled_at IS NULL AND (
            (current_session.company_link_id IS NULL AND NOT a.reset_required AND a.version=current_session.account_version)
            OR (current_session.company_link_id IS NOT NULL AND l.revoked_at IS NULL
                AND l.version=current_session.account_version AND l.policy_hash=ANY(policies)))
      ) THEN RETURN QUERY SELECT 'invalid',NULL::uuid,NULL::uuid,NULL::uuid,NULL::uuid,NULL::timestamptz,NULL::timestamptz,NULL::integer,NULL::text; RETURN; END IF;
    reused := current_session.refresh_hash<>previous_refresh;
    IF reused AND NOT EXISTS (SELECT FROM mnemion.spent_refresh_tokens h
      WHERE h.session_id=current_session.id AND h.token_hash=previous_refresh) THEN
      RETURN QUERY SELECT 'invalid',NULL::uuid,NULL::uuid,NULL::uuid,NULL::uuid,NULL::timestamptz,NULL::timestamptz,NULL::integer,NULL::text; RETURN;
    END IF;
    IF reused OR current_session.rotations>=4096 THEN
      UPDATE mnemion.api_keys k SET revoked_at=instant
        WHERE k.tenant_id=current_session.tenant_id AND k.id=current_session.key_id;
      PERFORM mnemion._sign_in_audit(current_session.tenant_id,current_session.principal_id,
        CASE WHEN reused THEN 'session.refresh_reused' ELSE 'session.refresh_limit' END,current_session.id);
      -- The caller commits this revocation before returning an HTTP error.
      RETURN QUERY SELECT 'revoked',NULL::uuid,NULL::uuid,NULL::uuid,NULL::uuid,NULL::timestamptz,NULL::timestamptz,NULL::integer,NULL::text; RETURN;
    END IF;
    INSERT INTO mnemion.spent_refresh_tokens(token_hash,session_id)
      VALUES(previous_refresh,current_session.id);
    UPDATE mnemion.sign_in_sessions s SET access_hash=access_digest,
      access_expires_at=least(instant+interval '15 minutes',s.expires_at),
      refresh_hash=refresh_digest,rotations=s.rotations+1,last_refreshed_at=instant
      WHERE s.id=current_session.id;
    RETURN QUERY SELECT 'ok',s.id,s.tenant_id,s.principal_id,s.key_id,s.access_expires_at,s.expires_at,s.rotations,CASE WHEN s.company_link_id IS NULL THEN 'password' ELSE 'company' END
      FROM mnemion.sign_in_sessions s WHERE s.id=current_session.id;
END $$;

REVOKE ALL ON FUNCTION mnemion.rotate_device_session(text,text,text,text,text,uuid,uuid,text[]) FROM PUBLIC,mnemion_worker;
GRANT EXECUTE ON FUNCTION mnemion.rotate_device_session(text,text,text,text,text,uuid,uuid,text[]) TO mnemion_app;
