-- Text-change chronology is private revision data, covered by the existing RLS
-- and revision deletion rules. Historical rows are interpreted conservatively;
-- no backfill rewrites their source evidence or creates new embedding jobs.
ALTER TABLE mnemion.memory_revisions
    ADD COLUMN passage_times jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(passage_times)='object');
