-- Existing custody retains its original mode-only policy. Never invent consent.
ALTER TABLE mnemion.capture_sources ADD COLUMN capture_policy jsonb
    CHECK(capture_policy IS NULL OR jsonb_typeof(capture_policy)='object');
