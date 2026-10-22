"""An already-authenticated SSH receiver only enqueues typed durable work."""

from . import HostControlError
from .protocol import MAX_RESPONSE, canonical, parse


def dispatch(store, actor, raw, host_status=None):
    request = parse(raw)
    # Every request, including a lookup of old work, needs current host authority.
    result, error = None, None
    try:
        authority = store.authority(actor, request.host_id)
        if request.action == "host.status":
            result = authority
            if host_status is not None:
                result = {**result, "service": host_status()}
        elif request.action == "operators.list":
            result = store.operators(
                actor, request.host_id, limit=request.limit, offset=request.offset
            )
        elif request.action == "operators.grant":
            result = store.grant(actor, request)
        elif request.action == "operators.revoke":
            result = store.revoke(actor, request)
        elif request.action == "operations.get":
            result = store.operation(actor, request.host_id, request.operation_id)
        elif request.action == "operations.list":
            result = store.operations(
                actor, request.host_id, limit=request.limit, offset=request.offset
            )
        else:
            result = store.enqueue(actor, request)
    except HostControlError as problem:
        error = {"code": problem.code, "message": str(problem)}
    response = {
        "protocol": 1,
        "host_id": str(request.host_id),
        "operator_id": str(actor),
        "request_id": str(request.request_id),
        "ok": error is None,
        "result": result,
        "error": error,
    }
    content = canonical(response)
    if len(content) > MAX_RESPONSE:
        raise HostControlError(
            "invalid_host_response", "The host control response exceeds its bound."
        )
    return content
