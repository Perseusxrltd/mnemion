"""Setup failures identify our code without disclosing provider error content."""

import json
import pytest

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


@pytest.mark.parametrize(
    "message,expected",
    [
        ("password authentication failed", "authentication"),
        ("no pg_hba.conf entry", "authentication"),
        ("connection timeout expired", "timeout"),
        ("connection timed out", "timeout"),
        ("Connection refused", "connection_refused"),
        ("target machine actively refused it", "connection_refused"),
        ("SSL error: decryption failed", "tls"),
        ("root certificate file does not exist", "tls"),
        ("server closed the connection unexpectedly", "connection_closed"),
        ("Connection reset by peer", "connection_closed"),
        ("Unrecognized provider detail", "other"),
    ],
)
def test_database_connection_classification_never_exports_driver_arguments(message, expected):
    private = "mnm_PRIVATE_TEST_CREDENTIAL /Users/private-workspace/password"
    driver_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    result = failure_diagnostic(driver_error(message + ": " + private))
    assert result == {"category": "database", "locations": [], "database_reason": expected}
    assert message not in json.dumps(result) and private not in json.dumps(result)


def test_database_classification_bounds_input_and_keeps_structured_authentication_state():
    driver_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    for value in ("connection refused" + "x" * 8192, object(), {"secret": "private"}):
        assert failure_diagnostic(driver_error(value))["database_reason"] == "other"
    authentication = type(
        "InvalidPassword", (driver_error,), {"__module__": "psycopg.errors", "sqlstate": "28P01"}
    )
    assert failure_diagnostic(authentication("private")) == {
        "category": "database",
        "locations": [],
        "sqlstate": "28P01",
        "database_reason": "authentication",
    }
    timeout = type(
        "ConnectionTimeout",
        (driver_error,),
        {"__module__": "psycopg.errors", "__str__": lambda _: pytest.fail("Do not format errors")},
    )
    assert failure_diagnostic(timeout())["database_reason"] == "timeout"
