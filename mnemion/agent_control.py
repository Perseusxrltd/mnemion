"""Discoverable, bounded agent operations over the existing authenticated API."""

from __future__ import annotations

import hashlib
import json
import re
import time
from functools import lru_cache
from importlib.resources import files
from typing import BinaryIO
from urllib.parse import quote

import httpx
from jsonschema import Draft202012Validator, FormatChecker

from .sdk import Client, MnemionError, _retry_after
from .version import __version__

INPUT_LIMIT = 2_000_000
INLINE_LIMIT = 262_144
DOWNLOAD_LIMIT = 1024**3


class ControlError(MnemionError):
    def __init__(
        self, code, message, *, status=422, request_id=None, outcome="not_sent", retry_after=None
    ):
        super().__init__(status, code, message, request_id, retry_after=retry_after)
        self.outcome = outcome
        self.retry_safe = False

    @property
    def retryable(self) -> bool:
        return self.retry_safe and super().retryable


@lru_cache(maxsize=1)
def _operations() -> dict:
    contract = json.loads(
        files("mnemion.service").joinpath("agent_contract.json").read_text(encoding="utf-8")
    )
    if contract["schema_version"] != 1:
        raise RuntimeError("Unsupported installed agent contract")
    return {operation["name"]: operation for operation in contract["operations"]}


def describe(name: str) -> dict:
    operation = _operations().get(name) if isinstance(name, str) and len(name) <= 100 else None
    if operation is None:
        raise ControlError(
            "unknown_operation", "Use the operation catalog to choose a supported name"
        )
    # Callers must not be able to change the process-wide routing policy.
    return json.loads(json.dumps(operation))


def catalog(*, group: str | None = None, query: str | None = None, offset=0, limit=20) -> dict:
    if (
        type(offset) is not int
        or type(limit) is not int
        or not 0 <= offset <= 10000
        or not 1 <= limit <= 100
    ):
        raise ControlError("invalid_page", "Use offset 0–10000 and limit 1–100")
    if any(
        value is not None and (not isinstance(value, str) or len(value) > 200)
        for value in (group, query)
    ):
        raise ControlError("invalid_filter", "Use a group or query of at most 200 characters")
    all_operations = list(_operations().values())
    selected = [
        operation
        for operation in all_operations
        if (not group or operation["group"] == group)
        and (
            not query
            or query.casefold() in (operation["name"] + " " + operation["summary"]).casefold()
        )
    ]
    fields = ("name", "group", "summary", "effect", "retry", "download", "sensitive_result")
    return {
        "schema_version": 1,
        "api_version": "v1",
        "package_version": __version__,
        "groups": sorted({operation["group"] for operation in all_operations}),
        "items": [
            {key: operation[key] for key in fields}
            for operation in selected[offset : offset + limit]
        ],
        "total": len(selected),
        "next_offset": offset + limit if offset + limit < len(selected) else None,
        "authorization": "Catalog entries describe API capabilities. Each request still requires the caller's current tenant, space and role permissions.",
    }


@lru_cache(maxsize=128)
def _validator(name):
    return Draft202012Validator(_operations()[name]["input_schema"], format_checker=FormatChecker())


def prepare(
    name: str, request: dict | None = None, *, effect: str | None = None
) -> tuple[dict, dict]:
    operation = describe(name)
    if effect is not None and operation["effect"] != effect:
        raise ControlError("wrong_effect", "Use the matching read or write operation tool")
    request = {} if request is None else request
    try:
        encoded = json.dumps(request, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise ControlError("invalid_request", "Use a finite JSON request object") from None
    if len(encoded) > INPUT_LIMIT:
        raise ControlError(
            "request_too_large", "The request exceeds the 2 MB API limit", status=413
        )
    # Freeze the validated envelope so a caller cannot mutate routing/body data
    # between validation and a retry of the same logical operation.
    request = json.loads(encoded)
    failure = next(_validator(name).iter_errors(request), None)
    if failure is not None:
        # Validator messages can contain memory text or credentials; never echo them.
        raise ControlError(
            "invalid_request", "The request does not match this operation's input_schema"
        )
    path, parameters = operation["path"], request.get("parameters", {})
    query = {}
    for key, value in parameters.items():
        if operation["parameter_locations"][key] == "path":
            text = str(value)
            if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", text) or text in {".", ".."}:
                raise ControlError("invalid_path_parameter", "Use one safe path component")
            path = path.replace("{" + key + "}", quote(text, safe=""))
        elif value is not None:
            query[key] = value
    return operation, {
        "method": operation["method"],
        "path": path,
        "params": query,
        "body": request.get("body"),
        "key": request.get("idempotency_key"),
    }


def _request_id(response: httpx.Response) -> str | None:
    value = response.headers.get("X-Request-ID", "")
    return value if re.fullmatch(r"[A-Za-z0-9-]{1,100}", value) else None


def _read_bytes(response, maximum, deadline, *, sink=None):
    if response.headers.get("Content-Encoding", "identity").lower() not in {"", "identity"}:
        raise ControlError(
            "unexpected_encoding",
            "The server must honor Accept-Encoding: identity",
            outcome="unknown",
        )
    length = response.headers.get("Content-Length")
    if length is not None and (not re.fullmatch(r"[0-9]{1,10}", length) or int(length) > maximum):
        raise ControlError(
            "response_too_large",
            "Use a smaller page, or the CLI with a private output file",
            status=413,
            request_id=_request_id(response),
            outcome="unknown",
        )
    data, size, digest = bytearray(), 0, hashlib.sha256()
    # In-process and MockTransport responses may already have been consumed.
    # Do not coalesce tiny network chunks: the wall-clock budget must also be
    # checked while a peer slowly trickles bytes below the socket idle timeout.
    chunks = (response.content,) if response.is_stream_consumed else response.iter_raw()
    for chunk in chunks:
        if time.monotonic() > deadline:
            raise ControlError(
                "response_deadline",
                "The bounded response deadline was exceeded",
                status=504,
                request_id=_request_id(response),
                outcome="unknown",
            )
        size += len(chunk)
        if size > maximum:
            raise ControlError(
                "response_too_large",
                "Use a smaller page, or the CLI with a private output file",
                status=413,
                request_id=_request_id(response),
                outcome="unknown",
            )
        digest.update(chunk)
        if sink is None:
            data.extend(chunk)
        else:
            try:
                written = sink.write(chunk)
            except OSError:
                written = None
            if written != len(chunk):
                raise ControlError(
                    "output_write_failed",
                    "The private output could not be completed",
                    outcome="unknown",
                )
    if length is not None and size != int(length):
        raise ControlError(
            "incomplete_response",
            "The response was interrupted",
            status=502,
            request_id=_request_id(response),
            outcome="unknown",
        )
    return bytes(data), size, digest.hexdigest()


def execute(
    client: Client,
    name: str,
    request: dict | None = None,
    *,
    effect: str | None = None,
    max_response_bytes: int = 65_536,
    output: BinaryIO | None = None,
) -> dict:
    """Call one reviewed operation; stream downloads to a caller-owned private file.

    Unknown-outcome mutations without server-supported idempotency never retry.
    An output stream receives only successful download bodies, not error pages.
    """
    operation, prepared = prepare(name, request, effect=effect)
    if operation["download"] != (output is not None):
        raise ControlError(
            "download_required" if operation["download"] else "unexpected_output",
            "Download operations use mnemion-control call --output; JSON results use the normal result object",
        )
    if type(max_response_bytes) is not int or not 1024 <= max_response_bytes <= (
        DOWNLOAD_LIMIT if output is not None else INLINE_LIMIT
    ):
        raise ControlError("invalid_response_limit", "Choose a supported bounded response size")
    headers = {
        "Accept-Encoding": "identity",
        "Accept": "*/*" if output is not None else "application/json",
    }
    if prepared["key"] is not None:
        headers["Idempotency-Key"] = prepared["key"]
    safe_retry = operation["retry"] == "read" or (
        operation["retry"] == "idempotency_key" and prepared["key"] is not None
    )
    retries = client.retries if safe_retry else 0
    started = time.monotonic()
    deadline = started + (900 if output is not None else 90)
    initial_position = output.tell() if output is not None else None
    for attempt in range(retries + 1):
        if time.monotonic() >= deadline:
            raise ControlError(
                "response_deadline",
                "The bounded response deadline was exceeded",
                status=504,
                outcome="unknown",
            )
        request_id = None
        try:
            with client._http.stream(
                prepared["method"],
                prepared["path"],
                params=prepared["params"],
                json=prepared["body"],
                headers=headers,
                timeout=httpx.Timeout(
                    **{
                        key: min(
                            value if value is not None else 30,
                            max(0.1, deadline - time.monotonic()),
                        )
                        for key, value in client._http.timeout.as_dict().items()
                    }
                ),
            ) as response:
                request_id = _request_id(response)
                if not response.is_success:
                    payload, _, _ = _read_bytes(response, 65_536, deadline)
                    delay = max(min(2, 0.2 * 2**attempt), _retry_after(response) or 0)
                    if (
                        response.status_code in {408, 429, 502, 503, 504}
                        and attempt < retries
                        and time.monotonic() + delay < deadline
                    ):
                        time.sleep(delay)
                        continue
                    try:
                        error = json.loads(payload).get("error", {})
                        code = error.get("code", "http_error")
                        if not isinstance(code, str) or not re.fullmatch(r"[a-z0-9_]{1,100}", code):
                            code = "http_error"
                    except (ValueError, AttributeError):
                        code = "http_error"
                    raise ControlError(
                        code,
                        f"Mnemion returned HTTP {response.status_code}",
                        status=response.status_code,
                        request_id=request_id,
                        outcome="unknown" if response.status_code >= 500 else "rejected",
                        retry_after=_retry_after(response),
                    )
                payload, size, digest = _read_bytes(
                    response, max_response_bytes, deadline, sink=output
                )
                if output is not None:
                    expected = response.headers.get("X-Content-SHA256")
                    if expected is not None and expected != digest:
                        raise ControlError(
                            "response_hash_mismatch",
                            "The attachment hash did not match",
                            status=502,
                            request_id=request_id,
                            outcome="unknown",
                        )
                    result = None
                else:
                    try:
                        result = None if response.status_code == 204 else json.loads(payload)
                    except (ValueError, RecursionError):
                        raise ControlError(
                            "invalid_response",
                            "The server returned an invalid JSON result; inspect state before retrying a write",
                            status=502,
                            request_id=request_id,
                            outcome="unknown",
                        ) from None
                return {
                    "operation": name,
                    "result": result,
                    "request_id": request_id,
                    "status": response.status_code,
                    "response_bytes": size,
                    "response_sha256": digest,
                    "attempts": attempt + 1,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                }
        except ControlError as error:
            error.retry_safe = safe_retry
            raise
        except httpx.TransportError:
            # A partially written download is left for the owner to discard. Do
            # not silently truncate an arbitrary caller-provided output stream.
            partially_written = output is not None and output.tell() != initial_position
            if attempt >= retries or partially_written or time.monotonic() >= deadline:
                error = ControlError(
                    "transport_error",
                    "The connection failed; inspect durable state before retrying a write without an idempotency key",
                    status=503,
                    request_id=request_id,
                    outcome="unknown",
                )
                error.retry_safe = safe_retry
                raise error from None
            time.sleep(min(2, 0.2 * 2**attempt))
    raise RuntimeError("Agent request retry loop exhausted")
