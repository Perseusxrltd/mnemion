"""A closing control socket never proves exit or repeats a shutdown request."""

import http.client
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from mnemion.host_control import installation, lifecycle
from mnemion.service import supervision
from service_tests.test_host_control_installation import prepared_host as prepared_host

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Unix managed host control")


@pytest.fixture
def shutting_down(prepared_host, monkeypatch):
    service, control, operator, _, port = prepared_host
    installation.adopt(control, service, operator, port=port)
    rpc = MagicMock()
    monkeypatch.setattr(supervision, "_rpc", rpc)
    clock = SimpleNamespace(elapsed=0.0)
    monkeypatch.setattr(
        lifecycle,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock.elapsed,
            sleep=lambda seconds: setattr(clock, "elapsed", clock.elapsed + seconds),
        ),
    )
    return control, rpc.return_value.__enter__.return_value.supervisor.shutdown


@pytest.mark.parametrize(
    "disconnect", [ConnectionResetError, BrokenPipeError, http.client.RemoteDisconnected]
)
@pytest.mark.parametrize("lost_shutdown_reply", [False, True])
def test_shutdown_observes_exit_after_disconnect_without_resubmitting(
    shutting_down, monkeypatch, disconnect, lost_shutdown_reply
):
    control, shutdown = shutting_down
    if lost_shutdown_reply:
        shutdown.side_effect = disconnect()
    observed = Mock(
        side_effect=[
            {"running": True},
            disconnect(),
            {"running": True},
            {"running": False},
        ]
    )
    monkeypatch.setattr(lifecycle, "status", observed)

    assert lifecycle.stop(control) == {"stopped": True}
    assert observed.call_count == 4
    shutdown.assert_called_once_with()


def test_repeated_disconnect_requires_inspection_instead_of_claiming_exit(
    shutting_down, monkeypatch
):
    control, shutdown = shutting_down

    def status(_):
        if not shutdown.called:
            return {"running": True}
        raise ConnectionResetError()

    monkeypatch.setattr(lifecycle, "status", status)
    assert lifecycle.stop(control) == {"stopped": False, "inspection_required": True}
    shutdown.assert_called_once_with()


def test_shutdown_does_not_hide_a_changed_supervisor_identity(shutting_down, monkeypatch):
    control, shutdown = shutting_down
    monkeypatch.setattr(
        lifecycle,
        "status",
        Mock(
            side_effect=[
                {"running": True},
                supervision.SupervisionError(
                    "The local supervisor belongs to a different instance"
                ),
            ]
        ),
    )
    with pytest.raises(supervision.SupervisionError, match="different instance"):
        lifecycle.stop(control)
    shutdown.assert_called_once_with()
