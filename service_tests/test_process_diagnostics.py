from service_tests.process_diagnostics import failure_locations


def test_child_failure_report_excludes_log_messages_credentials_and_external_paths():
    content = """Traceback (most recent call last):
  File "/Users/private-person/project/mnemion/service/model_broker.py", line 91, in server_identity
    print("password=secret", "mnm_secret")
  File "/private/location/secret-name.py", line 6, in read
    value = secret
mnemion.local_state.LocalSetupError: secret memory text
"""
    assert failure_locations(content) == {
        "locations": [
            {"file": "mnemion/service/model_broker.py", "line": 91, "function": "server_identity"}
        ],
        "errors": ["LocalSetupError"],
    }


def test_supervision_failure_retains_code_locations_without_exception_details(monkeypatch, capsys):
    import json
    from types import SimpleNamespace
    from pathlib import Path

    from mnemion.service import supervision

    def failure(*args):
        raise OSError(22, "private credentials and source text")

    monkeypatch.setattr(supervision, "child", failure)
    assert (
        supervision.execute(SimpleNamespace(action="child", state_dir=Path("unused"), role="api"))
        == 2
    )
    output = capsys.readouterr().err
    assert "private credentials" not in output and "source text" not in output
    diagnostic = json.loads(output)["diagnostic"]
    assert diagnostic["errno"] == 22
    assert diagnostic["locations"][0]["function"] == "execute"
    assert failure_locations(output)["diagnostics"][0] == diagnostic
