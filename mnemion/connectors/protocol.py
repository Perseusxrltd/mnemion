"""Public adapter boundary for clouds, applications, and company source systems."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable
from uuid import UUID, uuid4

from ..sdk import Client
from ..service.connector_models import BatchInput, ConnectorItemInput, ScopeInput, SourceFileError
from ..service.models import MemoryInput, SourceInput


@dataclass(frozen=True)
class Scope:
    external_id: str
    name: str
    members: list[str]
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class SkippedDocument:
    """A file the inventory could not accept.

    Content failures leave abort_inventory false so later files still sync.
    A selected-file access failure sets abort_inventory so the scan stops
    without treating the unread path as deleted.
    """

    path: str
    code: str
    abort_inventory: bool = False

    def report(self) -> dict:
        return SourceFileError(
            path=self.path[:512],
            path_sha256=hashlib.sha256(self.path.encode()).hexdigest(),
            error_code=self.code,
        ).model_dump()


@dataclass(frozen=True)
class Document:
    external_id: str
    revision: str
    title: str
    text: str
    uri: str | None = None
    media_type: str = "text/plain"
    metadata: dict = field(default_factory=dict)
    normalize_conversations: bool = False

    def items(self) -> Iterable[ConnectorItemInput]:
        # A stable source identity, never a global cross-permission content hash.
        identifier = hashlib.sha256(self.external_id.encode()).hexdigest()
        text = self.text
        status = "text"
        if not text.strip():
            text = f"Empty source: {self.title}"
            status = "empty"
        original_hash = hashlib.sha256(self.text.encode()).hexdigest()
        for index, start in enumerate(range(0, len(text), 48000)):
            end = min(start + 48000, len(text))
            content = text[start:end]
            # Whitespace-only parts carry no useful evidence but must remain
            # representable in an authoritative inventory.
            if not content.strip():
                content = "Whitespace-only source segment."
                part_status = "whitespace"
            else:
                part_status = status
            metadata = {
                **self.metadata,
                "source_external_id": self.external_id,
                "source_revision": self.revision,
                "document_sha256": original_hash,
                "document_start": start,
                "document_end": end,
                "part": index,
                "extractor": "mnemion-text-v1",
                "extraction_status": part_status,
            }
            memory = MemoryInput(
                content=content,
                kind="note",
                subject=self.title[:500],
                metadata=metadata,
                source=SourceInput(
                    title=self.title[:300] or "Source",
                    uri=self.uri,
                    content=content,
                    media_type=self.media_type,
                ),
            )
            yield ConnectorItemInput(
                external_id=f"{identifier}:part:{index:06d}",
                revision=hashlib.sha256((self.revision + ":mnemion-text-v1").encode()).hexdigest(),
                memory=memory,
            )
        if self.normalize_conversations:
            from ..conversations import VERSION, parse

            for transcript in parse(self.text, self.external_id):
                companion = Document(
                    external_id=self.external_id + "#conversation:" + transcript.identifier,
                    revision=self.revision
                    + ":"
                    + VERSION
                    + ":"
                    + hashlib.sha256(transcript.text.encode()).hexdigest(),
                    title=transcript.title,
                    text=transcript.text,
                    uri=self.uri,
                    metadata={
                        **self.metadata,
                        "projection": VERSION,
                        "conversation_format": transcript.format,
                        "conversation_id": transcript.identifier[:512],
                        "conversation_turns": transcript.turns,
                        "raw_source_external_id": self.external_id,
                        "raw_document_sha256": original_hash,
                    },
                )
                yield from companion.items()


class ConnectorClient:
    """Implement new providers with the same permission and ingestion protocol."""

    def __init__(self, client: Client, connector_id: str | UUID):
        self.client, self.connector_id = client, str(UUID(str(connector_id)))

    def refresh(self, scope: Scope, *, lease_seconds=900) -> dict:
        command = ScopeInput(
            external_id=scope.external_id,
            name=scope.name,
            members=scope.members,
            observed_at=scope.observed_at,
            lease_seconds=lease_seconds,
        )
        return self.client.request(
            "POST",
            f"/v1/connectors/{self.connector_id}/scopes",
            body=command.model_dump(mode="json"),
            key="acl:" + uuid4().hex,
        )

    def suspend(self, space_id: str, reason="provider_unavailable") -> dict:
        return self.client.request(
            "POST",
            f"/v1/connector-scopes/{UUID(space_id)}/suspend",
            body={"reason": reason},
            key="suspend:" + uuid4().hex,
        )

    def scopes(self) -> Iterable[dict]:
        after = None
        while True:
            result = self.client.request(
                "GET",
                f"/v1/connectors/{self.connector_id}/scopes",
                params={"after": after} if after else None,
            )
            yield from result["items"]
            after = result["next_cursor"]
            if not after:
                break

    def sync(
        self,
        space_id: str,
        items: Iterable[ConnectorItemInput | None],
        *,
        mode="snapshot",
        checkpoint: str | Callable[[], str | None] | None = None,
        heartbeat=None,
        inventory_errors: Callable[[], dict] | None = None,
    ) -> dict:
        space_id = str(UUID(space_id))
        run = str(uuid4())
        path = f"/v1/connector-scopes/{space_id}/runs"
        self.client.request("POST", path, body={"run_id": run, "mode": mode}, key="run:" + run)
        path += "/" + run
        page, sequence, size = [], 0, 0
        outcomes = {}

        def commit():
            nonlocal sequence, page, size
            if heartbeat:
                heartbeat()
            command = BatchInput(
                sequence=sequence,
                items=page,
                checkpoint=checkpoint() if callable(checkpoint) else checkpoint,
            )
            result = self.client.request(
                "POST",
                path + "/pages",
                body=command.model_dump(mode="json"),
                key=f"{run}:{sequence}",
            )
            for item in result["items"]:
                outcomes[item["outcome"]] = outcomes.get(item["outcome"], 0) + 1
            sequence += 1
            page, size = [], 0

        for item in items:
            # Providers yield a progress marker after each remote page, even an
            # empty one. This renews the run lease without inventing memories.
            if item is None:
                commit()
                continue
            length = len(json.dumps(item.model_dump(mode="json"), ensure_ascii=False).encode())
            if length > 1_500_000:
                raise ValueError("An adapter item exceeds the connector page limit")
            if page and (len(page) >= 50 or size + length > 1_500_000):
                commit()
            page.append(item)
            size += length
        if page or not sequence:
            commit()
        errors = inventory_errors() if inventory_errors else {}
        finish = {"complete_inventory": mode == "snapshot" and not errors, **errors}
        while True:
            if heartbeat:
                heartbeat()
            result = self.client.request(
                "POST",
                path + "/finish",
                body=finish,
                key="finish:" + run,
            )
            if result["state"] == "completed":
                return {**result, "outcomes": outcomes}
