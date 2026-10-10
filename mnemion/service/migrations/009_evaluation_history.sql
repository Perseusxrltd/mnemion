-- Stable, bounded history pages do not load query labels or full run summaries.
CREATE INDEX evaluation_datasets_history
    ON mnemion.evaluation_datasets(tenant_id,space_id,created_at DESC,id DESC);
CREATE INDEX evaluation_runs_history
    ON mnemion.evaluation_runs(tenant_id,space_id,created_at DESC,id DESC);
