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
