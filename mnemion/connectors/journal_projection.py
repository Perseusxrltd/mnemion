"""Project the whole journal scope before returning any journal memory to sync."""

from contextlib import ExitStack
import io

from ..journal.format import JournalError, journal_candidate, parse_catalog, parse_file
from ..journal.index import journal_index
from ..journal.privacy import scan
from .protocol import Document


def project_documents(documents):
    # Normal sources incur no SQLite work. An entire journal scope is checked
    # before emitting its active memories, so file order cannot hide denials.
    with ExitStack() as stack:
        index = None
        catalogs = {}
        scanned = 0
        for document in documents:
            if document is None:
                yield None
                continue
            path = str(document.metadata.get("path", ""))
            if (
                path.lower().endswith(".json")
                and "mnemion-memory-journal-catalog" in document.text[:4096]
            ):
                catalog = parse_catalog(document.text.encode("utf-8"))
                if catalog.namespace in catalogs and catalogs[catalog.namespace] != catalog.records:
                    raise JournalError("journal_catalog_conflict")
                catalogs[catalog.namespace] = catalog.records
                if len(catalogs) > 1000:
                    raise JournalError("journal_catalog_limit")
                continue
            if not journal_candidate(path, document.text):
                yield document
                continue
            if index is None:
                index = stack.enter_context(journal_index())
            for entry in parse_file(io.BytesIO(document.text.encode("utf-8"))):
                index.add(entry, uri=document.uri)
                scanned += 1
                if scanned % 100 == 0:
                    yield None
        if index is not None:
            if index.inventories() != catalogs:
                raise JournalError("journal_incomplete_inventory")
            for entry in index.current():
                # Source ACLs still govern these observations. Claimed writers
                # remain provenance and cannot become local principals or grants.
                scan(entry, personal_data=False)
                yield Document(
                    external_id="journal:" + entry.origin,
                    revision=entry.digest,
                    title=entry.subject or "Saved memory",
                    text=entry.text,
                    uri=index.location(entry),
                    metadata={
                        "projection": "mnemion-journal-v1",
                        "journal_entry_id": str(entry.id),
                        "journal_origin": entry.origin,
                        "journal_writer": str(entry.writer),
                        "journal_version": entry.version,
                        "journal_kind": entry.kind,
                        "important": entry.important,
                        "source_updated_at": entry.ts.isoformat(),
                    },
                )
        elif any(catalogs.values()):
            raise JournalError("journal_incomplete_inventory")
