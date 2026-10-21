-- Bounded capture-status pages must not scan every historical job per memory.
CREATE INDEX jobs_revision_progress_idx
    ON mnemion.jobs(tenant_id,space_id,revision_id,generation_id)
    INCLUDE(state)
    WHERE state IN ('pending','leased','failed');
