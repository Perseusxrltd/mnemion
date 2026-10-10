import io
import subprocess

from mnemion.capture import shared


def test_hook_uses_only_explicit_configuration_and_failure_does_not_block_chat(
    tmp_path, monkeypatch, capsys
):
    config = tmp_path / "approved connector.json"
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 2)

    monkeypatch.setattr(shared.subprocess, "run", run)
    monkeypatch.setattr(
        shared.sys,
        "stdin",
        io.StringIO(
            '{"transcript_path":"/not/selected/private.jsonl", "session_id":"../../outside"}'
        ),
    )
    assert shared.main(["--config", str(config)]) == 0
    assert calls[0][0][-1] == str(config)
    assert all("private.jsonl" not in argument for argument in calls[0][0])
    result = capsys.readouterr()
    assert result.out.strip() == "{}" and "did not complete" in result.err
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(shared.sys, "stdin", io.StringIO('{"stop_hook_active":true}'))
    shared.main(["--config", str(config)])
    assert len(calls) == 1
