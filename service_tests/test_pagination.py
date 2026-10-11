"""Malformed cursors return a bounded client error before pagination queries."""

import base64
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.evaluations import history_page
from mnemion.service.memory import MemoryService


@pytest.mark.parametrize(
    "value", [1, True, {"private-cursor-sentinel": 1}, ["private-cursor-sentinel"], None]
)
def test_non_string_cursor_fields_are_invalid_at_service_and_http_boundaries(env, value):
    snapshot = datetime.now(timezone.utc).isoformat()

    def unexpected_transaction(*args, **kwargs):
        pytest.fail("A malformed cursor opened a pagination transaction")

    memory = MemoryService(SimpleNamespace(transaction=unexpected_transaction), None)
    with TestClient(create_app(env.db, env.embedder)) as client:
        client.headers["Authorization"] = "Bearer " + env.token
        for memory_cursor in (True, False):
            data = (
                {"after": value, "snapshot": snapshot, "space": str(env.space)}
                if memory_cursor
                else {"id": value, "at": snapshot, "space": str(env.space)}
            )
            cursor = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
            with pytest.raises(ServiceError) as error:
                if memory_cursor:
                    memory.list(env.owner, env.space, cursor=cursor)
                else:
                    history_page(env.space, cursor, 50, 200)
            assert error.value.status == 422 and error.value.code == "invalid_cursor"
            paths = (
                ["memories"]
                if memory_cursor
                else ["evaluations/datasets", "librarian/runs", "librarian/proposals"]
            )
            for path in paths:
                response = client.get(f"/v1/spaces/{env.space}/{path}", params={"cursor": cursor})
                assert response.status_code == 422
                assert response.json()["error"]["code"] == "invalid_cursor"
                assert (
                    "private-cursor-sentinel" not in response.text and cursor not in response.text
                )
