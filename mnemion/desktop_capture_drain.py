"""Deliver a paused device's saved queue without reading any producer files."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from . import desktop_capture as capture, local_state
from .connectors.capture_delivery import deliver
from .connectors.conversation_inbox import InboxError
from .desktop_sources import load
from .sdk import Client
from .service.models import Command


class Drain(Command):
    operation: Literal["capture_drain"]
    id: UUID
    expected_revision: str = Field(min_length=1, max_length=128)
    credential: str = Field(min_length=16, max_length=8192, pattern=r"^[\x21-\x7e]+$", repr=False)
    inbox_key: str = Field(min_length=44, max_length=44, repr=False)
    confirm: Literal[True]

    @field_validator("confirm", mode="before")
    @classmethod
    def confirmation(cls, value):
        if value is not True:
            raise ValueError("Confirm delivery of the paused source's saved queue")
        return value


def perform(root, value):
    request = Drain.model_validate(value)
    root = local_state.directory(root)
    with local_state.lock(root):
        current = load(root)
        if current.revision != request.expected_revision:
            raise InboxError("capture_settings_changed")
        source = next((item for item in current.sources if item.id == request.id), None)
        if source is None or source.enabled or not source.custody:
            raise InboxError("capture_settings_changed")
        with capture.opened(root, source, request.inbox_key) as (inbox, _):
            with Client(source.endpoint, request.credential, timeout=10, retries=0) as client:
                result = deliver(inbox, client)
            return {
                "format": "mnemion-capture-drained-v1",
                "id": str(source.id),
                "source_enabled": False,
                "remote_committed_events": result["remote_committed_events"],
                "delivery_complete": not result["pending_events"]
                and not result["unknown_pages"]
                and not result["fence_sweep_pending"],
                "status": inbox.status(),
            }
