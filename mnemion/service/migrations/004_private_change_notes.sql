-- Free-form review/correction reasons can contain memory text. Keep them in
-- the content lifecycle, separate from the retained operational audit receipt.
CREATE TABLE mnemion.memory_change_notes (
    tenant_id uuid NOT NULL,
    space_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    event_id uuid NOT NULL,
    reason text NOT NULL CHECK(length(reason) BETWEEN 1 AND 1000),
    PRIMARY KEY (tenant_id, event_id),
    FOREIGN KEY (tenant_id, space_id, memory_id) REFERENCES mnemion.memories(tenant_id, space_id, id),
    FOREIGN KEY (tenant_id, event_id) REFERENCES mnemion.audit_events(tenant_id, id)
);
INSERT INTO mnemion.memory_change_notes(tenant_id,space_id,memory_id,event_id,reason)
    SELECT a.tenant_id,a.space_id,m.id,a.id,a.details->>'reason'
    FROM mnemion.audit_events a JOIN mnemion.memories m
      ON m.tenant_id=a.tenant_id AND m.space_id=a.space_id AND m.id::text=a.resource_id
    WHERE a.action IN ('memory.revised','memory.reviewed') AND a.details ? 'reason'
      AND m.deleted_at IS NULL;
UPDATE mnemion.audit_events SET details=details-'reason'
    WHERE action IN ('memory.revised','memory.reviewed') AND details ? 'reason';
ALTER TABLE mnemion.memory_change_notes ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON mnemion.memory_change_notes TO mnemion_app;
GRANT SELECT, DELETE ON mnemion.memory_change_notes TO mnemion_worker;
CREATE POLICY change_note_read ON mnemion.memory_change_notes FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,30) AND EXISTS (
        SELECT FROM mnemion.memories m WHERE m.tenant_id=memory_change_notes.tenant_id
          AND m.space_id=memory_change_notes.space_id AND m.id=memory_change_notes.memory_id
          AND m.deleted_at IS NULL));
CREATE POLICY change_note_append ON mnemion.memory_change_notes FOR INSERT TO mnemion_app
    WITH CHECK (tenant_id=mnemion.tenant() AND mnemion.authorized(space_id,20));
CREATE POLICY change_note_worker ON mnemion.memory_change_notes TO mnemion_worker
    USING (tenant_id=mnemion.tenant()) WITH CHECK (tenant_id=mnemion.tenant());
DROP POLICY audit_read ON mnemion.audit_events;
CREATE POLICY audit_read ON mnemion.audit_events FOR SELECT TO mnemion_app
    USING (tenant_id=mnemion.tenant() AND (
        (space_id IS NULL AND mnemion.administrator()) OR
        (space_id IS NOT NULL AND mnemion.authorized(space_id,30))));
