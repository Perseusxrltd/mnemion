"""Setup failures identify our code without disclosing provider error content."""

import json

from mnemion.local_diagnostics import failure_diagnostic


def test_os_failure_never_includes_message_filename_locals_or_exception_class_name():
    private = "mnm_PRIVATE_TEST_CREDENTIAL /Users/private-workspace/password"
    try:
        raise OSError(13, private, private)
    except OSError as error:
        result = failure_diagnostic(error)
    assert result == {"category": "operating_system", "locations": [], "errno": 13}
    assert private not in json.dumps(result)


def test_only_bounded_own_code_locations_are_retained_without_source_lines():
    namespace = {"__name__": "mnemion.local_workspace", "credential": "private-fixture-secret"}
    exec(
        compile(
            "def fail(depth):\n"
            "    if depth: return fail(depth - 1)\n"
            "    raise RuntimeError(credential)\n",
            "/private/employee/company/workspace.py",
            "exec",
        ),
        namespace,
    )
    try:
        namespace["fail"](30)
    except RuntimeError as error:
        result = failure_diagnostic(error)
    assert result["category"] == "unexpected"
    assert len(result["locations"]) == 8
    assert all(location["module"] == "mnemion.local_workspace" for location in result["locations"])
    assert result["locations"][-1]["line"] == 3
    assert "private" not in json.dumps(result)


def test_unknown_exception_names_and_invalid_provider_codes_are_not_disclosed():
    error = type("private_secret", (Exception,), {"sqlstate": "private_secret"})("secret")
    assert failure_diagnostic(error) == {"category": "unexpected", "locations": []}
