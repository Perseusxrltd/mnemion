"""Authenticated vault endpoints. All secret reads are explicit and uncached."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query

from .contracts import Page
from .db import Identity
from . import keepass_vault
from .keepass_models import (
    KeepassExported,
    KeepassExportInput,
    KeepassImported,
    KeepassImportInput,
    KeepassPreview,
    KeepassPreviewInput,
)
from .vault import VaultService
from .vault_models import (
    VaultAuditEvent,
    VaultAuditor,
    VaultAuditorChange,
    VaultDelete,
    VaultDeleted,
    VaultEntry,
    VaultEnvelope,
    VaultExport,
    VaultGrant,
    VaultGrants,
    VaultImport,
    VaultPut,
    VaultStatus,
    VaultValue,
)


def attach_vault(app, service: VaultService, authenticated):
    Auth = Annotated[Identity, Depends(authenticated)]
    Offset = Annotated[int, Query(ge=0, le=10000)]
    Limit = Annotated[int, Query(ge=1, le=100)]

    @app.get("/v1/vault/status", response_model=VaultStatus, tags=["Vault"])
    def vault_status(identity: Auth):
        """Inspect vault availability and this connection's identity without returning secrets."""
        return service.status(identity)

    @app.get("/v1/vault/entries", response_model=Page[VaultEntry], tags=["Vault"])
    def vault_list(identity: Auth, offset: Offset = 0, limit: Limit = 100):
        """List permitted credential names and current versions; values are never included."""
        return service.list(identity, offset=offset, limit=limit)

    @app.get("/v1/vault/auditors", response_model=Page[VaultAuditor], tags=["Vault"])
    def vault_auditors(
        identity: Auth, offset: Offset = 0, limit: Limit = 100, key_id: UUID | None = None
    ):
        """Review exact-key metadata auditor grants as a workspace administrator."""
        return service.auditors(identity, offset=offset, limit=limit, key_id=key_id)

    @app.put("/v1/vault/auditors/{key_id}", response_model=VaultAuditor, tags=["Vault"])
    def vault_auditor(key_id: UUID, command: VaultAuditorChange, identity: Auth):
        """Grant or revoke vault-wide metadata and audit access, never value permissions."""
        return service.auditor(identity, key_id, command)

    @app.get("/v1/vault/entries/{entry_id}", response_model=VaultValue, tags=["Vault"])
    def vault_get(entry_id: UUID, identity: Auth):
        """Explicitly decrypt one currently authorized credential and audit its read."""
        return service.get(identity, entry_id)

    @app.put("/v1/vault/entries/{entry_id}", response_model=VaultEntry, tags=["Vault"])
    def vault_put(entry_id: UUID, command: VaultPut, identity: Auth):
        """Create as administrator, or replace an explicitly writable credential at its current version."""
        return service.put(identity, entry_id, command)

    @app.get("/v1/vault/entries/{entry_id}/grants", response_model=VaultGrants, tags=["Vault"])
    def vault_grants(entry_id: UUID, identity: Auth):
        """Review credential-specific grants as a workspace administrator."""
        return service.grants(identity, entry_id)

    @app.put("/v1/vault/entries/{entry_id}/grants", response_model=VaultGrants, tags=["Vault"])
    def vault_grant(entry_id: UUID, command: VaultGrant, identity: Auth):
        """Grant, narrow or revoke one person's or key's credential access with a revision check."""
        return service.grant(identity, entry_id, command)

    @app.post("/v1/vault/entries/{entry_id}/delete", response_model=VaultDeleted, tags=["Vault"])
    def vault_delete(entry_id: UUID, command: VaultDelete, identity: Auth):
        """Purge the current encrypted value and retain a deletion denial for recovery."""
        return service.delete(identity, entry_id, command)

    @app.post("/v1/vault/export", response_model=VaultEnvelope, tags=["Vault"])
    def vault_export(command: VaultExport, identity: Auth):
        """Export up to 100 readable credentials under a separate supplied recovery key."""
        return service.export(identity, command)

    @app.post("/v1/vault/import", response_model=Page[VaultEntry], tags=["Vault"])
    def vault_import(command: VaultImport, identity: Auth):
        """Verify an encrypted export and create new credentials without restoring historical grants."""
        return service.import_archive(identity, command)

    @app.post("/v1/vault/keepass/preview", response_model=KeepassPreview, tags=["Vault"])
    def keepass_preview(command: KeepassPreviewInput, identity: Auth):
        """Verify KDBX 4 in memory and review its masked current-field mapping as administrator."""
        return keepass_vault.preview(service, identity, command)

    @app.post("/v1/vault/keepass/import", response_model=KeepassImported, tags=["Vault"])
    def keepass_import(command: KeepassImportInput, identity: Auth):
        """Approve the exact preview, importing current fields atomically without historical grants."""
        return keepass_vault.import_file(service, identity, command)

    @app.post("/v1/vault/keepass/export", response_model=KeepassExported, tags=["Vault"])
    def keepass_export(command: KeepassExportInput, identity: Auth):
        """Export only explicitly readable credentials as password-encrypted KDBX 4.1."""
        return keepass_vault.export_file(service, identity, command)

    @app.get("/v1/vault/audit", response_model=Page[VaultAuditEvent], tags=["Vault"])
    def vault_audit(identity: Auth, offset: Offset = 0, limit: Limit = 100):
        """Review credential access events without recording or exposing values."""
        return service.audit_events(identity, offset=offset, limit=limit)
