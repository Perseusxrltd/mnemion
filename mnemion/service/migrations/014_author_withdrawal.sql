-- Author withdrawal cannot depend on a contributor seeing reviewer-only data.
-- Erase derived prose in the same transaction that denies the source memory.
CREATE FUNCTION mnemion.purge_withdrawn_memory_derivatives() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE affected record;
BEGIN
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.space_id IS DISTINCT FROM OLD.space_id
        OR NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION 'Memory identity cannot change during withdrawal' USING ERRCODE='23514';
    END IF;
    FOR affected IN
        SELECT proposal_id FROM mnemion.librarian_dependencies
        WHERE tenant_id=OLD.tenant_id AND space_id=OLD.space_id AND memory_id=OLD.id
    LOOP
        UPDATE mnemion.librarian_proposals SET state='invalidated',suggestion=NULL,
            version=version+1,previous_revision_id=NULL,applied_revision_id=NULL,applied_version=NULL
            WHERE tenant_id=OLD.tenant_id AND space_id=OLD.space_id AND id=affected.proposal_id;
        DELETE FROM mnemion.librarian_dependencies
            WHERE tenant_id=OLD.tenant_id AND space_id=OLD.space_id AND proposal_id=affected.proposal_id;
    END LOOP;
    DELETE FROM mnemion.librarian_observations
        WHERE tenant_id=OLD.tenant_id AND space_id=OLD.space_id AND memory_id=OLD.id;
    RETURN NEW;
END
$$;
REVOKE ALL ON FUNCTION mnemion.purge_withdrawn_memory_derivatives() FROM PUBLIC;
CREATE TRIGGER erase_withdrawn_memory_derivatives
    AFTER UPDATE OF deleted_at ON mnemion.memories
    FOR EACH ROW WHEN (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL)
    EXECUTE FUNCTION mnemion.purge_withdrawn_memory_derivatives();
