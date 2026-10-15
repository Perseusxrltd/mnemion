-- Company authentication can authorize an assistant without creating a password
-- or replacing the person's remembered Studio session.
ALTER TABLE mnemion.oauth_local_requests
    ADD COLUMN company_link_id uuid,
    ADD COLUMN company_expires_at timestamptz,
    ADD CONSTRAINT oauth_request_company_link FOREIGN KEY(tenant_id,principal_id,company_link_id)
      REFERENCES mnemion.company_links(tenant_id,principal_id,id),
    ADD CONSTRAINT oauth_request_company_pair CHECK (
      (company_link_id IS NULL AND company_expires_at IS NULL) OR
      (company_link_id IS NOT NULL AND company_expires_at IS NOT NULL
        AND tenant_id IS NOT NULL AND principal_id IS NOT NULL));

CREATE FUNCTION mnemion._local_oauth_company_valid(workspace uuid,person uuid,link uuid,
    expected_version uuid,deadline timestamptz,policies text[]) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT deadline>clock_timestamp() AND EXISTS (
      SELECT FROM mnemion.company_links l JOIN mnemion.principals p
        ON p.tenant_id=l.tenant_id AND p.id=l.principal_id
      WHERE l.tenant_id=workspace AND l.principal_id=person AND l.id=link
        AND l.version=expected_version AND l.revoked_at IS NULL AND l.policy_hash=ANY(policies)
        AND p.disabled_at IS NULL AND p.kind='human')
$$;

CREATE FUNCTION mnemion.local_oauth_company_login(ticket text,expected_issuer text,expected_resource text,
    workspace uuid,state_digest text,verifier_digest text,idp_issuer text,idp_client text,
    idp_subject text,external_hash text,policy text,seconds integer,proof text,browser text)
    RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE request mnemion.oauth_local_requests%ROWTYPE; login mnemion.company_login_requests%ROWTYPE;
    linked mnemion.company_links%ROWTYPE; preview jsonb; instant timestamptz; deadline timestamptz;
BEGIN
    IF seconds NOT BETWEEN 900 AND 86400 THEN RETURN NULL; END IF;
    PERFORM mnemion._sign_in_lock(workspace);
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE ticket_hash=ticket
      AND issuer=expected_issuer AND resource=expected_resource FOR UPDATE;
    IF NOT FOUND OR request.expires_at<=clock_timestamp() OR request.code_hash IS NOT NULL
      OR request.consumed_at IS NOT NULL THEN RETURN NULL; END IF;
    SELECT * INTO login FROM mnemion.company_login_requests WHERE state_hash=state_digest
      AND proof_hash=verifier_digest AND tenant_id=workspace AND policy_hash=policy
      AND claimed_at IS NOT NULL AND completed_at IS NULL AND expires_at>clock_timestamp()
      AND payload->>'transport'='browser' AND payload->>'invitation_hash' IS NULL
      AND payload->'consent'=jsonb_build_object('ticket_hash',ticket,'browser_hash',browser) FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT * INTO linked FROM mnemion.company_links WHERE tenant_id=workspace
      AND provider_id=login.provider_id AND identity_hash=external_hash AND policy_hash=policy
      AND issuer=idp_issuer AND client_id=idp_client AND subject=idp_subject AND revoked_at IS NULL;
    IF NOT FOUND OR NOT EXISTS (SELECT FROM mnemion.principals WHERE tenant_id=workspace
      AND id=linked.principal_id AND kind='human' AND disabled_at IS NULL) THEN RETURN NULL; END IF;
    instant := clock_timestamp();
    deadline := instant+make_interval(secs=>seconds);
    preview := mnemion._local_oauth_permissions(workspace,linked.principal_id);
    UPDATE mnemion.oauth_local_requests SET tenant_id=workspace,principal_id=linked.principal_id,
      account_version=linked.version,company_link_id=linked.id,company_expires_at=deadline,
      proof_hash=proof,browser_hash=browser,permissions=preview WHERE id=request.id;
    UPDATE mnemion.company_login_requests SET completed_at=instant WHERE state_hash=state_digest;
    UPDATE mnemion.company_links SET last_authenticated_at=instant WHERE id=linked.id;
    PERFORM mnemion._sign_in_audit(workspace,linked.principal_id,'oauth.company_authenticated',request.id);
    RETURN jsonb_build_object('permissions',preview,'expires_at',deadline);
END $$;

CREATE FUNCTION mnemion.local_oauth_consent_current(ticket text,expected_issuer text,
    expected_resource text,proof text,browser text,code text,policies text[]) RETURNS jsonb
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE request mnemion.oauth_local_requests%ROWTYPE;
BEGIN
    SELECT * INTO request FROM mnemion.oauth_local_requests
      WHERE ticket_hash=ticket AND issuer=expected_issuer AND resource=expected_resource;
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF request.company_link_id IS NULL THEN
      RETURN mnemion.local_oauth_consent(ticket,expected_issuer,expected_resource,proof,browser,code);
    END IF;
    PERFORM mnemion._sign_in_lock(request.tenant_id);
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE id=request.id FOR UPDATE;
    IF request.expires_at<=clock_timestamp() OR request.code_hash IS NOT NULL
      OR request.consumed_at IS NOT NULL OR request.proof_hash IS DISTINCT FROM proof
      OR request.browser_hash IS DISTINCT FROM browser OR NOT coalesce(mnemion._local_oauth_company_valid(
        request.tenant_id,request.principal_id,request.company_link_id,request.account_version,
        request.company_expires_at,policies),false)
      OR mnemion._local_oauth_permissions(request.tenant_id,request.principal_id)
        IS DISTINCT FROM request.permissions THEN RETURN NULL; END IF;
    UPDATE mnemion.oauth_local_requests SET code_hash=code,
      code_expires_at=least(clock_timestamp()+interval '2 minutes',company_expires_at),
      proof_hash=NULL,browser_hash=NULL WHERE id=request.id;
    PERFORM mnemion._sign_in_audit(request.tenant_id,request.principal_id,'oauth.consent',request.id);
    RETURN request.parameters;
END $$;

CREATE FUNCTION mnemion.local_oauth_exchange_current(code text,client text,expected_issuer text,
    expected_resource text,session_uuid uuid,key_uuid uuid,anchor_hash text,access_digest text,
    refresh_digest text,label text,policies text[]) RETURNS jsonb
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE request mnemion.oauth_local_requests%ROWTYPE; instant timestamptz; access_deadline timestamptz;
BEGIN
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE code_hash=code AND client_id=client
      AND issuer=expected_issuer AND resource=expected_resource;
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF request.company_link_id IS NULL THEN
      RETURN mnemion.local_oauth_exchange(code,client,expected_issuer,expected_resource,session_uuid,
        key_uuid,anchor_hash,access_digest,refresh_digest,label);
    END IF;
    PERFORM mnemion._sign_in_lock(request.tenant_id);
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE id=request.id FOR UPDATE;
    instant := clock_timestamp();
    IF request.code_expires_at<=instant THEN RETURN NULL; END IF;
    IF request.consumed_at IS NOT NULL THEN
      UPDATE mnemion.api_keys k SET revoked_at=coalesce(k.revoked_at,instant)
        FROM mnemion.sign_in_sessions s WHERE s.id=request.session_id AND k.id=s.key_id;
      RETURN jsonb_build_object('error','code_reused');
    END IF;
    IF NOT coalesce(mnemion._local_oauth_company_valid(request.tenant_id,request.principal_id,
        request.company_link_id,request.account_version,request.company_expires_at,policies),false)
      OR mnemion._local_oauth_permissions(request.tenant_id,request.principal_id)
        IS DISTINCT FROM request.permissions THEN RETURN NULL; END IF;
    IF (SELECT count(*) FROM mnemion.sign_in_sessions s JOIN mnemion.api_keys k
      ON k.tenant_id=s.tenant_id AND k.id=s.key_id WHERE s.tenant_id=request.tenant_id
      AND s.principal_id=request.principal_id AND s.expires_at>instant AND k.revoked_at IS NULL)>=32
      THEN RETURN NULL; END IF;
    access_deadline := least(instant+interval '15 minutes',request.company_expires_at);
    INSERT INTO mnemion.api_keys(tenant_id,id,principal_id,name,token_hash,prefix,expires_at,session_key)
      VALUES(request.tenant_id,key_uuid,request.principal_id,'Company assistant session',anchor_hash,
        'session',request.company_expires_at,true);
    INSERT INTO mnemion.sign_in_sessions(id,tenant_id,principal_id,key_id,account_version,device_name,
      transport,access_hash,access_expires_at,refresh_hash,csrf_hash,created_at,last_refreshed_at,expires_at,company_link_id)
      VALUES(session_uuid,request.tenant_id,request.principal_id,key_uuid,request.account_version,label,
        'native',access_digest,access_deadline,refresh_digest,NULL,instant,instant,
        request.company_expires_at,request.company_link_id);
    INSERT INTO mnemion.oauth_local_connections(session_id,tenant_id,principal_id,client_id,issuer,resource,scopes)
      VALUES(session_uuid,request.tenant_id,request.principal_id,client,expected_issuer,expected_resource,ARRAY['mnemion:access']);
    UPDATE mnemion.oauth_local_requests SET consumed_at=instant,session_id=session_uuid WHERE id=request.id;
    PERFORM mnemion._sign_in_audit(request.tenant_id,request.principal_id,'oauth.company_connected',session_uuid);
    RETURN jsonb_build_object('session_id',session_uuid,'access_expires_at',extract(epoch FROM access_deadline),
      'expires_at',extract(epoch FROM request.company_expires_at));
END $$;

CREATE FUNCTION mnemion.local_oauth_token_current(digest text,token_kind text,expected_issuer text,
    expected_resource text,policies text[]) RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT coalesce(mnemion.local_oauth_token(digest,token_kind,expected_issuer,expected_resource),(
      SELECT jsonb_build_object('session_id',s.id,'tenant_id',s.tenant_id,'principal_id',s.principal_id,
        'key_id',s.key_id,'client_id',c.client_id,'scopes',c.scopes,
        'expires_at',extract(epoch FROM CASE WHEN token_kind='access' THEN s.access_expires_at ELSE s.expires_at END))
      FROM mnemion.oauth_local_connections c JOIN mnemion.sign_in_sessions s
        ON s.id=c.session_id AND s.tenant_id=c.tenant_id AND s.principal_id=c.principal_id
      JOIN mnemion.api_keys k ON k.id=s.key_id AND k.tenant_id=s.tenant_id AND k.principal_id=s.principal_id
      WHERE c.issuer=expected_issuer AND c.resource=expected_resource AND s.transport='native'
        AND k.revoked_at IS NULL AND k.expires_at>clock_timestamp() AND k.session_key
        AND mnemion._local_oauth_company_valid(s.tenant_id,s.principal_id,s.company_link_id,
          s.account_version,s.expires_at,policies)
        AND ((token_kind='access' AND s.access_hash=digest AND s.access_expires_at>clock_timestamp())
          OR (token_kind='refresh' AND (s.refresh_hash=digest OR EXISTS
            (SELECT FROM mnemion.spent_refresh_tokens h WHERE h.session_id=s.id AND h.token_hash=digest))))))
$$;

CREATE FUNCTION mnemion.local_oauth_refresh_current(previous_refresh text,client text,
    expected_issuer text,expected_resource text,access_digest text,refresh_digest text,policies text[])
    RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE token jsonb; rotated record;
BEGIN
    token := mnemion.local_oauth_token_current(previous_refresh,'refresh',expected_issuer,expected_resource,policies);
    IF token IS NULL OR token->>'client_id'<>client THEN RETURN NULL; END IF;
    SELECT * INTO rotated FROM mnemion.rotate_device_session(previous_refresh,access_digest,refresh_digest,
      NULL,'native',(token->>'tenant_id')::uuid,(token->>'session_id')::uuid,policies);
    IF rotated.result IS DISTINCT FROM 'ok' THEN RETURN jsonb_build_object('error','invalid_refresh'); END IF;
    RETURN jsonb_build_object('session_id',rotated.session_id,
      'access_expires_at',extract(epoch FROM rotated.access_expires_at),'expires_at',extract(epoch FROM rotated.expires_at));
END $$;

CREATE FUNCTION mnemion.local_oauth_revoke_current(digest text,kind text,client text,
    expected_issuer text,expected_resource text,policies text[]) RETURNS void
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE token jsonb;
BEGIN
    token := mnemion.local_oauth_token_current(digest,kind,expected_issuer,expected_resource,policies);
    IF token IS NULL OR token->>'client_id'<>client THEN RETURN; END IF;
    PERFORM mnemion._sign_in_lock((token->>'tenant_id')::uuid);
    UPDATE mnemion.api_keys SET revoked_at=coalesce(revoked_at,clock_timestamp()) WHERE id=(token->>'key_id')::uuid;
    PERFORM mnemion._sign_in_audit((token->>'tenant_id')::uuid,(token->>'principal_id')::uuid,
      'oauth.revoked',(token->>'session_id')::uuid);
END $$;

REVOKE ALL ON FUNCTION mnemion._local_oauth_company_valid(uuid,uuid,uuid,uuid,timestamptz,text[])
    FROM PUBLIC,mnemion_app,mnemion_worker;
REVOKE ALL ON FUNCTION
    mnemion.local_oauth_company_login(text,text,text,uuid,text,text,text,text,text,text,text,integer,text,text),
    mnemion.local_oauth_consent_current(text,text,text,text,text,text,text[]),
    mnemion.local_oauth_exchange_current(text,text,text,text,uuid,uuid,text,text,text,text,text[]),
    mnemion.local_oauth_token_current(text,text,text,text,text[]),
    mnemion.local_oauth_refresh_current(text,text,text,text,text,text,text[]),
    mnemion.local_oauth_revoke_current(text,text,text,text,text,text[]) FROM PUBLIC,mnemion_worker;
GRANT EXECUTE ON FUNCTION
    mnemion.local_oauth_company_login(text,text,text,uuid,text,text,text,text,text,text,text,integer,text,text),
    mnemion.local_oauth_consent_current(text,text,text,text,text,text,text[]),
    mnemion.local_oauth_exchange_current(text,text,text,text,uuid,uuid,text,text,text,text,text[]),
    mnemion.local_oauth_token_current(text,text,text,text,text[]),
    mnemion.local_oauth_refresh_current(text,text,text,text,text,text,text[]),
    mnemion.local_oauth_revoke_current(text,text,text,text,text,text[]) TO mnemion_app;

-- Preserve old personal flows while preventing a company proof from using
-- their password-only policy checks. Consent login cannot issue a Studio session.
CREATE OR REPLACE FUNCTION mnemion.local_oauth_login(
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
      account_version=expected_version,company_link_id=NULL,company_expires_at=NULL,
      proof_hash=proof,browser_hash=browser,permissions=preview
      WHERE id=request.id;
    RETURN preview;
END $$;

CREATE OR REPLACE FUNCTION mnemion.local_oauth_consent(
    ticket text,expected_issuer text,expected_resource text,proof text,browser text,code text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE request mnemion.oauth_local_requests%ROWTYPE; preview jsonb;
BEGIN
    SELECT * INTO request FROM mnemion.oauth_local_requests
      WHERE ticket_hash=ticket AND issuer=expected_issuer AND resource=expected_resource;
    IF NOT FOUND OR request.tenant_id IS NULL OR request.company_link_id IS NOT NULL THEN RETURN NULL; END IF;
    PERFORM mnemion._sign_in_lock(request.tenant_id);
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE id=request.id FOR UPDATE;
    IF request.company_link_id IS NOT NULL THEN RETURN NULL; END IF;
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

CREATE OR REPLACE FUNCTION mnemion.local_oauth_exchange(
    code text,client text,expected_issuer text,expected_resource text,session_uuid uuid,key_uuid uuid,
    anchor_hash text,access_digest text,refresh_digest text,label text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE request mnemion.oauth_local_requests%ROWTYPE; account mnemion.password_accounts%ROWTYPE;
  issued mnemion.sign_in_sessions%ROWTYPE;
BEGIN
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE code_hash=code AND client_id=client
      AND issuer=expected_issuer AND resource=expected_resource;
    IF NOT FOUND OR request.tenant_id IS NULL OR request.company_link_id IS NOT NULL THEN RETURN NULL; END IF;
    PERFORM mnemion._sign_in_lock(request.tenant_id);
    SELECT * INTO request FROM mnemion.oauth_local_requests WHERE id=request.id FOR UPDATE;
    IF request.company_link_id IS NOT NULL THEN RETURN NULL; END IF;
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

CREATE OR REPLACE FUNCTION mnemion.local_oauth_token(digest text,token_kind text,expected_issuer text,expected_resource text)
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
      AND s.company_link_id IS NULL
      AND p.disabled_at IS NULL AND NOT a.reset_required AND a.version=s.account_version
      AND ((token_kind='access' AND s.access_hash=digest AND s.access_expires_at>clock_timestamp())
        OR (token_kind='refresh' AND (s.refresh_hash=digest OR EXISTS
          (SELECT FROM mnemion.spent_refresh_tokens h WHERE h.session_id=s.id AND h.token_hash=digest))))
$$;

CREATE OR REPLACE FUNCTION mnemion.issue_company_session(state_digest text,proof_digest text,issuer_url text,
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
    IF NOT FOUND OR seconds NOT BETWEEN 900 AND 86400 OR request.payload ? 'consent' THEN RETURN; END IF;
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
