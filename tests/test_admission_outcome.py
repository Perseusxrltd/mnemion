"""Sanitized admission outcomes. Arrays must not throw, and true is not version 1."""

from deploy.admission_outcome import (
    admission_diagnostic_enabled,
    public_admission_fields,
    sanitize_admission_outcome,
    unknown_admission_outcome,
)

SECRET = "mnm_private_fixture_key"
PATH = "C:\\Users\\secret\\probe.json"
VALID_GUARD = {
    "schema_version": 1,
    "network": "unmetered",
    "constrained": True,
    "reason": "cpu_unobserved",
    "path": PATH,
    "credential": SECRET,
}


def test_diagnostic_flag_is_explicit_text():
    assert admission_diagnostic_enabled(None) is False
    assert admission_diagnostic_enabled([]) is False
    assert admission_diagnostic_enabled({}) is False
    assert admission_diagnostic_enabled({"MNEMION_TELEMETRY_RESOURCE_ADMISSION": 1}) is False
    assert admission_diagnostic_enabled({"MNEMION_TELEMETRY_RESOURCE_ADMISSION": True}) is False
    assert admission_diagnostic_enabled({"MNEMION_TELEMETRY_RESOURCE_ADMISSION": "true"}) is False
    assert admission_diagnostic_enabled({"MNEMION_TELEMETRY_RESOURCE_ADMISSION": "1"}) is True


def test_corrupt_fields_match_the_javascript_sanitizer():
    cases = [
        (None, None),
        ([], None),
        ("reserved", None),
        ({"schema_version": 1, "outcome": ["reserved"]}, None),
        ({"schema_version": 1, "outcome": {"stage": "reserved"}}, None),
        ({"schema_version": True, "outcome": "reserved"}, None),
        ({"schema_version": "1", "outcome": "reserved"}, None),
        ({"schema_version": 1, "outcome": "nope", "path": PATH}, None),
        (
            {"schema_version": 1, "outcome": "reserved", "guard": [], "secret": SECRET},
            {"schema_version": 1, "outcome": "reserved", "guard": None},
        ),
        (
            {
                "schema_version": 1,
                "outcome": "prepare_refused",
                "guard": {**VALID_GUARD, "network": ["unmetered"]},
                "token": SECRET,
            },
            {"schema_version": 1, "outcome": "prepare_refused", "guard": None},
        ),
        (
            {
                "schema_version": 1,
                "outcome": "aborted",
                "guard": {**VALID_GUARD, "schema_version": True},
            },
            {"schema_version": 1, "outcome": "aborted", "guard": None},
        ),
        (
            {
                "schema_version": 1,
                "outcome": "reserve_refused",
                "guard": {**VALID_GUARD, "reason": {"code": "memory"}},
            },
            {"schema_version": 1, "outcome": "reserve_refused", "guard": None},
        ),
        (
            {
                "schema_version": 1,
                "outcome": "reserved",
                "guard": {**VALID_GUARD, "constrained": 1},
            },
            {"schema_version": 1, "outcome": "reserved", "guard": None},
        ),
        (
            {
                "schema_version": 1,
                "outcome": "eligible_refused",
                "guard": VALID_GUARD,
                "api_key": SECRET,
            },
            {"schema_version": 1, "outcome": "eligible_refused", "guard": None},
        ),
        (
            {"schema_version": 1, "outcome": "unknown", "guard": VALID_GUARD, "path": PATH},
            {"schema_version": 1, "outcome": "unknown", "guard": None},
        ),
        (
            {"schema_version": 1, "outcome": "prepare_refused", "guard": VALID_GUARD, "secret": SECRET},
            {
                "schema_version": 1,
                "outcome": "prepare_refused",
                "guard": {
                    "schema_version": 1,
                    "network": "unmetered",
                    "constrained": True,
                    "reason": "cpu_unobserved",
                },
            },
        ),
    ]
    for raw, expected in cases:
        got = sanitize_admission_outcome(raw)
        assert got == expected
        assert SECRET not in str(got)
        assert "Users" not in str(got)
        if got is not None:
            assert set(got) == {"schema_version", "outcome", "guard"}
    # JavaScript has one number type, so 1.0 === 1. Python must not treat float 1.0 as version 1.
    assert sanitize_admission_outcome({"schema_version": 1.0, "outcome": "reserved"}) is None


def test_public_fields_keep_one_stage_or_unknown():
    assert public_admission_fields({}, {}) == {}
    assert public_admission_fields([], {"admission_diagnostic": True}) == {
        "admission_diagnostic": True,
        "admission_outcome": unknown_admission_outcome(),
    }
    dirty = {
        "admission_diagnostic": True,
        "admission_outcome": {
            "schema_version": 1,
            "outcome": ["reserved"],
            "guard": {"network": {"kind": "wifi"}},
            "api_key": SECRET,
        },
    }
    assert public_admission_fields(dirty, {}) == {
        "admission_diagnostic": True,
        "admission_outcome": unknown_admission_outcome(),
    }
    kept = public_admission_fields(
        {
            "admission_diagnostic": True,
            "admission_outcome": {
                "schema_version": 1,
                "outcome": "reserved",
                "guard": {**VALID_GUARD, "network": ["unmetered"]},
                "api_key": SECRET,
            },
        },
        {},
    )
    assert kept == {
        "admission_diagnostic": True,
        "admission_outcome": {"schema_version": 1, "outcome": "reserved", "guard": None},
    }
    assert SECRET not in str(kept)
