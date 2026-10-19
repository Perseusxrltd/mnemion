"""Atomic per-operation receipts before batching into public daily JSONL files."""

import os
from uuid import UUID, uuid4

from .. import local_state
from ..private_input import read_private
from ..private_output import private_output
from .config import Destination
from .format import JournalEntry, JournalError, MAX_LINE_BYTES, parse_line


class Spool:
    def __init__(self, destination: Destination):
        self.destination = destination
        self.root = local_state.directory(destination.state_directory)
        self.pending = local_state.directory(self.root / "pending")
        marker = self.root / "journal-owner.json"
        owner = {
            "format": "mnemion-journal-state",
            "tenant_id": str(destination.tenant_id),
            "space_id": str(destination.space_id),
            "destination_id": destination.id,
        }
        try:
            local_state.write(marker, owner, replace=False)
        except FileExistsError:
            if local_state.read(marker) != owner:
                raise JournalError("journal_state_owner_mismatch") from None

    def record(self, entry: JournalEntry):
        if (entry.tenant_id, entry.space_id) != (
            self.destination.tenant_id,
            self.destination.space_id,
        ):
            raise JournalError("journal_scope_mismatch")
        value = entry.line()
        with local_state.lock(self.root):
            self._record(entry, value)

    def _record(self, entry, value):
        directory = local_state.directory(self.pending / str(entry.memory_id))
        target = directory / (str(entry.id) + ".json")
        if target.exists() or target.is_symlink():
            if read_private(target, maximum=MAX_LINE_BYTES) != value:
                raise JournalError("journal_entry_conflict")
            return
        temporary = directory / (".entry-" + uuid4().hex)
        try:
            with private_output(temporary) as stream:
                stream.write(value)
            os.replace(temporary, target)
            local_state._sync_directory(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def records(self, *, limit=None):
        """Caller holds the spool lock when coordinating a publish or cleanup."""
        count = 0
        for directory in self.pending.iterdir():
            try:
                memory = UUID(directory.name)
            except ValueError:
                raise JournalError("unexpected_journal_state") from None
            local_state._regular(directory, directory=True)
            for path in directory.iterdir():
                if path.name.startswith(".entry-"):
                    continue  # An uncommitted temporary receipt is never published.
                try:
                    entry_id = UUID(path.stem)
                except ValueError:
                    raise JournalError("unexpected_journal_state") from None
                if path.suffix != ".json":
                    raise JournalError("unexpected_journal_state")
                entry = parse_line(read_private(path, maximum=MAX_LINE_BYTES))
                if entry.id != entry_id or entry.memory_id != memory:
                    raise JournalError("journal_state_identity_mismatch")
                if (entry.tenant_id, entry.space_id) != (
                    self.destination.tenant_id,
                    self.destination.space_id,
                ):
                    raise JournalError("journal_scope_mismatch")
                yield entry
                count += 1
                if limit is not None and count >= limit:
                    return

    def acknowledge(self, entries):
        """Remove only exact private receipts after the remote acknowledged them."""
        for entry in entries:
            path = self.pending / str(entry.memory_id) / (str(entry.id) + ".json")
            if read_private(path, maximum=MAX_LINE_BYTES) != entry.line():
                raise JournalError("journal_entry_conflict")
            path.unlink()
            local_state._sync_directory(path.parent)
            try:
                path.parent.rmdir()
            except OSError:
                pass
        local_state._sync_directory(self.pending)

    def forget_pending_content(self, entry: JournalEntry):
        if entry.action != "forget":
            raise JournalError("journal_denial_required")
        with local_state.lock(self.root):
            if (entry.tenant_id, entry.space_id) != (
                self.destination.tenant_id,
                self.destination.space_id,
            ):
                raise JournalError("journal_scope_mismatch")
            self._record(entry, entry.line())
            directory = self.pending / str(entry.memory_id)
            for path in directory.iterdir():
                if path.name == str(entry.id) + ".json":
                    continue
                local_state._regular(path)
                # This affects un-published private spool files only. Existing
                # Git history is retained; the new denial prevents replay.
                path.unlink()
            local_state._sync_directory(directory)
