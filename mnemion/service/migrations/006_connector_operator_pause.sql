-- An operator pause is sticky. A routine successful provider check cannot undo
-- a human pause; resuming still requires a fresh permission observation.
ALTER TABLE mnemion.connector_scopes ADD COLUMN operator_paused boolean NOT NULL DEFAULT false;
UPDATE mnemion.connector_scopes SET operator_paused=true WHERE suspension_reason='operator_paused';
CREATE FUNCTION mnemion.guard_connector_pause() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NEW.suspension_reason='operator_paused' THEN NEW.operator_paused:=true; END IF;
    IF TG_OP='UPDATE' AND OLD.operator_paused AND NEW.operator_paused AND NEW.suspended_at IS NULL THEN
        RAISE EXCEPTION 'Connector scope is paused by an operator' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER connector_pause_guard BEFORE INSERT OR UPDATE ON mnemion.connector_scopes
    FOR EACH ROW EXECUTE FUNCTION mnemion.guard_connector_pause();
CREATE FUNCTION mnemion.resume_connector_scope(space uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NOT mnemion.administrator() OR NOT mnemion.managed_scope(space) THEN
        RAISE insufficient_privilege;
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('connector:'||space::text,0));
    UPDATE mnemion.connector_scopes SET operator_paused=false,suspended_at=now(),
      suspension_reason='provider_unavailable',access_valid_until=least(access_valid_until,now())
      WHERE tenant_id=mnemion.tenant() AND space_id=space;
END
$$;
REVOKE ALL ON FUNCTION mnemion.guard_connector_pause(),mnemion.resume_connector_scope(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mnemion.resume_connector_scope(uuid) TO mnemion_app;
