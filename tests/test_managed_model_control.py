"""Model control must never infer process ownership from a server name."""

from types import SimpleNamespace
import subprocess
import sys
from mnemion import local_state
from mnemion.managed_model_process import ModelController

import pytest

from mnemion import cli, llm_backend


@pytest.mark.parametrize(
    "platform,script",
    [("linux", "/model/start.sh"), ("win32", "start.sh"), ("win32", "wsl:///model/start.sh")],
)
def test_unowned_stop_never_runs_a_process_name_kill(tmp_path, monkeypatch, platform, script):
    calls = []
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a))
    backend = llm_backend.ManagedBackend("http://127.0.0.1:1", "synthetic", start_script=script)
    assert backend.stop() is False
    assert calls == []


def test_wsl_script_path_is_one_argument_and_is_not_rewritten(monkeypatch):
    launches = []

    class Backend(llm_backend.ManagedBackend):
        def _controller(self):
            return SimpleNamespace(launch=lambda argv: launches.append(argv))

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_kw: launches.append(argv))
    monkeypatch.setattr(sys, "platform", "linux")
    script = "/model/folder with spaces/start; untouched.sh"
    backend = Backend("http://127.0.0.1:1", "synthetic", start_script="wsl://" + script)
    backend._launch()
    assert len(launches) == 1
    assert launches[0][-2:] == ["bash", script]
    assert "-c" not in launches[0] and not any("sed -i" in part for part in launches[0])


@pytest.mark.parametrize(
    "reply,expected",
    [(None, 1), ("", 1), ("WRONG_REPLY", 1), ({"error": "not assistant text"}, 1), ("disabled", 2)],
)
def test_llm_test_reports_real_failure_to_agents(monkeypatch, capsys, reply, expected):
    backend = (
        llm_backend.NullBackend()
        if reply == "disabled"
        else SimpleNamespace(
            info=lambda: "synthetic backend",
            chat=lambda *_a, **_kw: reply,
        )
    )
    monkeypatch.setattr("mnemion.config.MnemionConfig", lambda: SimpleNamespace(llm={}))
    monkeypatch.setattr(llm_backend, "get_backend", lambda _config: backend)
    monkeypatch.setattr(cli, "_configure_stdio", lambda: None)
    monkeypatch.setattr("sys.argv", ["mnemion", "--no-telemetry", "llm", "test"])
    with pytest.raises(SystemExit) as stopped:
        cli.main()
    assert stopped.value.code == expected
    assert "Test PASSED" not in capsys.readouterr().out


def test_failed_or_unowned_stop_cannot_trigger_a_restart(monkeypatch):
    calls = []
    backend = llm_backend.ManagedBackend(
        "http://127.0.0.1:1", "synthetic", start_script="start.sh", startup_timeout=0
    )
    monkeypatch.setattr(backend, "stop", lambda **_kw: False)
    backend._model_controller = SimpleNamespace(restart=lambda *_a, **_kw: False)
    monkeypatch.setattr(backend, "_launch", lambda: calls.append("launch"))
    monkeypatch.setattr(llm_backend._time, "sleep", lambda _seconds: None)
    backend._restart()
    assert calls == []


def test_attaching_to_an_existing_server_does_not_start_an_idle_killer(monkeypatch):
    calls = []

    class Backend(llm_backend.ManagedBackend):
        def _controller(self):
            return SimpleNamespace(owned=lambda: False)

    backend = Backend("http://127.0.0.1:1", "synthetic", start_script="start.sh")
    monkeypatch.setattr(backend, "ping", lambda: True)
    monkeypatch.setattr(backend, "_start_idle_watcher", lambda: calls.append("watcher"))
    assert backend.ensure_running() is True
    assert calls == []


def test_cli_stop_does_not_claim_an_unverified_model_stopped(monkeypatch, capsys):
    backend = llm_backend.ManagedBackend("http://127.0.0.1:1", "synthetic", start_script="start.sh")
    monkeypatch.setattr(backend, "ping", lambda: True)
    monkeypatch.setattr(backend, "stop", lambda: False)
    monkeypatch.setattr(llm_backend, "get_backend", lambda _config: backend)
    monkeypatch.setattr("mnemion.config.MnemionConfig", lambda: SimpleNamespace(llm={}))
    with pytest.raises(SystemExit) as stopped:
        cli.cmd_llm(SimpleNamespace(llm_action="stop"))
    assert stopped.value.code == 2
    assert "Stopped" not in capsys.readouterr().out


@pytest.mark.parametrize("suffix,first", [(".ps1", "powershell.exe"), (".exe", None)])
def test_native_windows_launch_keeps_the_path_as_one_argument(tmp_path, monkeypatch, suffix, first):
    launches = []

    class Backend(llm_backend.ManagedBackend):
        def _controller(self):
            return SimpleNamespace(launch=lambda argv: launches.append(argv))

    script = tmp_path / ("model with spaces" + suffix)
    monkeypatch.setattr(sys, "platform", "win32")
    Backend("http://127.0.0.1:1", "synthetic", start_script=str(script))._launch()
    assert launches[0][-1] == str(script)
    if first:
        assert launches[0][0].endswith(first)
        assert launches[0][-2] == "-File"
        assert "-Command" not in launches[0]
    else:
        assert launches == [[str(script)]]


def test_named_wsl_distribution_is_respected(monkeypatch):
    launches = []

    class Backend(llm_backend.ManagedBackend):
        def _controller(self):
            return SimpleNamespace(launch=lambda argv: launches.append(argv))

    Backend("http://127.0.0.1:1", "synthetic", start_script="wsl://Debian/home/model.sh")._launch()
    assert launches[0][1:3] == ["-d", "Debian"]
    assert launches[0][-1] == "/home/model.sh"


def test_exact_model_test_reply_passes_without_a_provider_call(monkeypatch, capsys):
    calls = []

    def chat(messages, **options):
        calls.append((messages, options))
        return "  MNEMION_OK\n"

    monkeypatch.setattr("mnemion.config.MnemionConfig", lambda: SimpleNamespace(llm={}))
    monkeypatch.setattr(
        llm_backend,
        "get_backend",
        lambda _config: SimpleNamespace(info=lambda: "synthetic", chat=chat),
    )
    assert cli.cmd_llm(SimpleNamespace(llm_action="test")) is None
    assert "Test PASSED" in capsys.readouterr().out
    assert len(calls) == 1 and calls[0][1] == {"max_tokens": 20}


@pytest.mark.parametrize("kind,code", [("disabled", 2), ("external", 2), ("timeout", 1)])
def test_model_start_failure_has_a_nonzero_exit(monkeypatch, kind, code):
    if kind == "disabled":
        backend = llm_backend.NullBackend()
    elif kind == "external":
        backend = SimpleNamespace(info=lambda: "external")
    else:
        backend = llm_backend.ManagedBackend(
            "http://127.0.0.1:1", "synthetic", start_script="start.sh"
        )
        monkeypatch.setattr(backend, "ping", lambda: False)
        monkeypatch.setattr(backend, "ensure_running", lambda: False)
    monkeypatch.setattr("mnemion.config.MnemionConfig", lambda: SimpleNamespace(llm={}))
    monkeypatch.setattr(llm_backend, "get_backend", lambda _config: backend)
    with pytest.raises(SystemExit) as stopped:
        cli.cmd_llm(SimpleNamespace(llm_action="start"))
    assert stopped.value.code == code


@pytest.mark.parametrize("interrupted", [False, True])
def test_actual_backend_wrapper_holds_a_request_lease(tmp_path, monkeypatch, interrupted):
    controller = ModelController(tmp_path / "custody")
    controller.launch([sys.executable, "-c", "import time;time.sleep(120)"])
    backend = llm_backend.ManagedBackend("http://127.0.0.1:1", "synthetic", start_script="start.sh")
    backend._model_controller = controller

    def response(*_a, **_kw):
        assert local_state.read(controller.path)["leases"]
        assert not ModelController(controller.root).stop(only_unused=True)
        if interrupted:
            raise KeyboardInterrupt
        return "MNEMION_OK"

    monkeypatch.setattr(llm_backend.OpenAICompatBackend, "chat", response)
    try:
        if interrupted:
            with pytest.raises(KeyboardInterrupt):
                backend.chat([])
        else:
            assert backend.chat([]) == "MNEMION_OK"
        assert local_state.read(controller.path)["leases"] == {}
    finally:
        controller.stop()


def test_still_reachable_endpoint_is_not_reported_stopped(monkeypatch, capsys):
    backend = llm_backend.ManagedBackend("http://127.0.0.1:1", "synthetic", start_script="start.sh")
    monkeypatch.setattr(backend, "ping", lambda: True)
    monkeypatch.setattr(backend, "stop", lambda: True)
    monkeypatch.setattr(llm_backend, "get_backend", lambda _config: backend)
    monkeypatch.setattr("mnemion.config.MnemionConfig", lambda: SimpleNamespace(llm={}))
    with pytest.raises(SystemExit) as stopped:
        cli.cmd_llm(SimpleNamespace(llm_action="stop"))
    assert stopped.value.code == 1
    assert "Stopped" not in capsys.readouterr().out


def test_replacement_model_gets_its_own_idle_watcher(monkeypatch):
    launches = []

    class Thread:
        def __init__(self, **kwargs):
            launches.append(kwargs)

        def start(self):
            pass

        def is_alive(self):
            return True

    backend = llm_backend.ManagedBackend("http://127.0.0.1:1", "synthetic", start_script="start.sh")
    backend._model_controller = SimpleNamespace(
        owned=lambda: True, launch_identity=lambda: "new-launch"
    )
    backend._idle_thread = SimpleNamespace(is_alive=lambda: True)
    backend._idle_launch = "previous-launch"
    monkeypatch.setattr(llm_backend.threading, "Thread", Thread)
    backend._start_idle_watcher()
    backend._start_idle_watcher()
    assert len(launches) == 1 and launches[0]["args"] == ("new-launch",)


def test_relative_scripts_in_different_directories_do_not_share_custody(tmp_path, monkeypatch):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(first)
    left = llm_backend.ManagedBackend(
        "http://127.0.0.1:1", "synthetic", start_script="start.sh"
    )._controller()
    monkeypatch.chdir(second)
    right = llm_backend.ManagedBackend(
        "http://127.0.0.1:1", "synthetic", start_script="start.sh"
    )._controller()
    assert left.root != right.root
    assert not left.root.exists() and not right.root.exists()


def test_unreachable_model_still_uses_recorded_process_control(monkeypatch):
    calls = []
    backend = llm_backend.ManagedBackend("http://127.0.0.1:1", "synthetic", start_script="start.sh")
    monkeypatch.setattr(backend, "ping", lambda: False)
    monkeypatch.setattr(backend, "stop", lambda: calls.append("stop") or True)
    monkeypatch.setattr(llm_backend, "get_backend", lambda _config: backend)
    monkeypatch.setattr("mnemion.config.MnemionConfig", lambda: SimpleNamespace(llm={}))
    cli.cmd_llm(SimpleNamespace(llm_action="stop"))
    assert calls == ["stop"]
