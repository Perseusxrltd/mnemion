"""Reply metadata stays per-call, bounded and separate from immutable bodies."""

import httpx
import pytest

from mnemion.sdk import Client, RequestReceipt
from mnemion.service.request_replay import capture_stored, observed, request_replay


@pytest.mark.parametrize(
    "disposition,count,expected",
    [
        ("new", "0", 0),
        ("new", "50", 50),
        ("new", "51", None),
        ("new", "01", None),
        ("new", "-1", None),
        ("new", "1.0", None),
        ("new", " 1", None),
        ("new", "PRIVATE_FIELD", None),
        ("replayed", "2", None),
        ("unknown", "2", None),
        (None, None, None),
    ],
)
def test_only_fixed_reply_metadata_is_retained(disposition, count, expected):
    headers = {"X-Request-ID": "PRIVATE_REQUEST", "X-Unrelated": "PRIVATE_HEADER"}
    if disposition is not None:
        headers["X-Mnemion-Idempotency"] = disposition
    if count is not None:
        headers["X-Mnemion-Capture-Stored"] = count
    body = {"items": [{"content": "PRIVATE_BODY"}]}
    with Client(
        "https://example.invalid",
        "fixture-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body, headers=headers)),
    ) as client:
        value, metadata = client.request_with_receipt("POST", "/page", body=body, key="fixed")
    assert value == body
    assert metadata.disposition == (disposition if disposition in {"new", "replayed"} else None)
    assert metadata.capture_stored_events == expected
    assert "PRIVATE" not in repr(metadata)


def test_retry_keeps_the_original_key_and_observes_only_the_replayed_reply(monkeypatch):
    requests = []
    monkeypatch.setattr("mnemion.sdk.time.sleep", lambda _: None)

    def reply(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("Synthetic lost reply", request=request)
        return httpx.Response(
            200,
            json={"durable": True},
            headers={"X-Mnemion-Idempotency": "replayed", "X-Mnemion-Capture-Stored": "7"},
        )

    with Client(
        "https://example.invalid", "fixture-key", transport=httpx.MockTransport(reply)
    ) as client:
        body, metadata = client.request_with_receipt("POST", "/page", body={}, key="same-page")
    assert body == {"durable": True}
    assert len(requests) == 2
    assert {request.headers["Idempotency-Key"] for request in requests} == {"same-page"}
    assert metadata.disposition == "replayed" and metadata.capture_stored_events is None


def test_reused_metadata_is_cleared_before_an_unconfirmed_request():
    metadata = RequestReceipt("new", 3)

    def unavailable(request):
        raise httpx.ReadTimeout("Synthetic unavailable reply", request=request)

    with Client(
        "https://example.invalid",
        "fixture-key",
        retries=0,
        transport=httpx.MockTransport(unavailable),
    ) as client:
        with pytest.raises(httpx.ReadTimeout):
            client.request("POST", "/page", key="same-page", receipt=metadata)
    assert metadata == RequestReceipt()


def test_nested_writes_cannot_replace_the_page_owner_or_its_effect():
    with request_replay() as page:
        owner = observed(False)
        nested = observed(True)
        capture_stored(nested, 20)
        assert page.value == "new" and page.capture_stored_events is None
        capture_stored(owner, 2)
        capture_stored(owner, 9)
        assert page.capture_stored_events == 2
        with request_replay() as other:
            capture_stored(owner, 4)
            assert other.value is None and other.capture_stored_events is None
    with request_replay() as replay:
        capture_stored(observed(True), 1)
        assert replay.value == "replayed" and replay.capture_stored_events is None
