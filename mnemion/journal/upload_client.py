"""Bounded Python transport for native journals; approval is a separate step."""

import base64
import hashlib
from typing import BinaryIO, Callable
from uuid import UUID, uuid4

from ..service.journal_upload_models import (
    CHUNK_BYTES,
    JournalUploadAdvance,
    JournalUploadChunk,
    JournalUploadChunkReceipt,
    JournalUploadDecisions,
    JournalUploadFiles,
    JournalUploadInput,
    JournalUploadList,
    JournalUploadStatus,
)


def _path(space, upload=None):
    path = f"/v1/spaces/{UUID(str(space))}/journal-recovery/uploads"
    return path if upload is None else path + f"/{UUID(str(upload))}"


class JournalUploadClient:
    """Client mixin: HTTP request/retry policy is owned by the normal SDK."""

    def begin_journal_upload(
        self, space_id: str, command: JournalUploadInput, *, idempotency_key: str | None = None
    ) -> JournalUploadStatus:
        command = JournalUploadInput.model_validate(command)
        body = command.model_dump(mode="json")
        body["catalog"] = command.catalog.get_secret_value()
        return JournalUploadStatus.model_validate(
            self.request("POST", _path(space_id), body=body, key=idempotency_key or str(uuid4()))
        )

    def list_journal_uploads(self, space_id: str) -> JournalUploadList:
        return JournalUploadList.model_validate(self.request("GET", _path(space_id)))

    def journal_upload(self, space_id: str, upload_id: str) -> JournalUploadStatus:
        return JournalUploadStatus.model_validate(self.request("GET", _path(space_id, upload_id)))

    def journal_upload_files(
        self, space_id: str, upload_id: str, *, cursor: int = 0
    ) -> JournalUploadFiles:
        return JournalUploadFiles.model_validate(
            self.request("GET", _path(space_id, upload_id) + "/files", params={"cursor": cursor})
        )

    def journal_upload_decisions(
        self, space_id: str, upload_id: str, *, cursor: int = 0
    ) -> JournalUploadDecisions:
        return JournalUploadDecisions.model_validate(
            self.request(
                "GET", _path(space_id, upload_id) + "/decisions", params={"cursor": cursor}
            )
        )

    def send_journal_chunk(
        self, space_id: str, upload_id: str, file_index: int, command: JournalUploadChunk
    ) -> JournalUploadChunkReceipt:
        if type(file_index) is not int or not 0 <= file_index < 8192:
            raise ValueError("Use a declared journal file index")
        command = JournalUploadChunk.model_validate(command)
        body = command.model_dump(mode="json")
        body["data"] = command.data.get_secret_value()
        return JournalUploadChunkReceipt.model_validate(
            self.request("PUT", _path(space_id, upload_id) + f"/files/{file_index}", body=body)
        )

    def advance_journal_upload(
        self, space_id: str, upload_id: str, command: JournalUploadAdvance
    ) -> JournalUploadStatus:
        command = JournalUploadAdvance.model_validate(command)
        return JournalUploadStatus.model_validate(
            self.request(
                "POST",
                _path(space_id, upload_id) + "/advance",
                body=command.model_dump(mode="json"),
            )
        )

    def upload_journal_file(
        self,
        space_id: str,
        upload_id: str,
        file_index: int,
        source: BinaryIO,
        *,
        progress: Callable[[JournalUploadStatus], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> JournalUploadStatus:
        """Verify the acknowledged prefix before resuming one seekable binary file.

        The caller owns the stream and may pause between chunks. After a network
        failure, call this again with the same original file; no approval occurs.
        """
        file = next(
            (
                item
                for item in self.journal_upload_files(space_id, upload_id, cursor=file_index).items
                if item.index == file_index
            ),
            None,
        )
        if file is None:
            raise ValueError("The declared journal file is unavailable")
        source.seek(0, 2)
        if source.tell() != file.bytes:
            raise ValueError("The journal file length changed; use the original selection")
        source.seek(0)
        chain, offset = "0" * 64, 0
        while offset < file.received:
            if cancelled and cancelled():
                return self.journal_upload(space_id, upload_id)
            data = source.read(min(CHUNK_BYTES, file.received - offset))
            if not data:
                raise ValueError("The journal file was truncated")
            chain = hashlib.sha256(
                bytes.fromhex(chain)
                + offset.to_bytes(8, "big")
                + len(data).to_bytes(8, "big")
                + hashlib.sha256(data).digest()
            ).hexdigest()
            offset += len(data)
        if chain != file.transport_sha256:
            raise ValueError(
                "The journal file differs from its acknowledged prefix; start a new upload"
            )
        status = self.journal_upload(space_id, upload_id)
        while offset < file.bytes and not (cancelled and cancelled()):
            data = source.read(min(CHUNK_BYTES, file.bytes - offset))
            if len(data) != min(CHUNK_BYTES, file.bytes - offset):
                raise ValueError("The journal file was truncated")
            receipt = self.send_journal_chunk(
                space_id,
                upload_id,
                file_index,
                JournalUploadChunk(
                    offset=offset,
                    sha256=hashlib.sha256(data).hexdigest(),
                    data=base64.b64encode(data).decode(),
                ),
            )
            offset += len(data)
            status = receipt.upload
            if progress:
                progress(status)
        return status
