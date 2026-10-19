-- Original KeePass grouping/field labels stay encrypted, including when their
-- ordinary vault display names are masked. They never enter the search schema.
ALTER TABLE mnemion.vault_entries
    ADD COLUMN keepass_nonce bytea,
    ADD COLUMN keepass_ciphertext bytea,
    ADD CONSTRAINT vault_keepass_envelope CHECK (
      (keepass_nonce IS NULL AND keepass_ciphertext IS NULL)
      OR (deleted_at IS NULL AND keepass_nonce IS NOT NULL AND keepass_ciphertext IS NOT NULL
          AND octet_length(keepass_nonce)=12
          AND octet_length(keepass_ciphertext) BETWEEN 17 AND 32784));
ALTER TABLE mnemion.vault_audit_events DROP CONSTRAINT vault_audit_events_action_check;
ALTER TABLE mnemion.vault_audit_events ADD CONSTRAINT vault_audit_events_action_check
    CHECK (action IN ('list','get','put','grant','delete','export','import',
                     'keepass_preview','keepass_import','keepass_export'));
