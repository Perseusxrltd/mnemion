"""Company browser policy accepts exact origins and preserves default clients."""

import json

import pytest

from mnemion.service import studio_policy as policy


def test_default_browser_connections_remain_compatible(monkeypatch):
    monkeypatch.delenv(policy.VARIABLE, raising=False)
    assert policy.content_security_policy() == (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self' https: http://127.0.0.1:* http://localhost:*; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )


def test_restricted_browser_policy_keeps_same_origin_and_explicit_local_bridge(monkeypatch):
    monkeypatch.setenv(policy.VARIABLE, "[]")
    assert "connect-src 'self';" in policy.content_security_policy()
    monkeypatch.setenv(
        policy.VARIABLE,
        json.dumps(["https://MEMORY.example/", "http://[::1]:4321", "https://memory.example"]),
    )
    assert policy.configuration() == {
        "profile": "restricted",
        "origins": ["https://memory.example", "http://[::1]:4321"],
    }


@pytest.mark.parametrize(
    "value",
    [
        "https:",
        "https://*.example",
        "https://private@example.com",
        "https://example.com/private",
        "https://example.com/?private",
        "https://example.com/#private",
        "https://example.com;private",
        "https://example.com\nprivate",
        "http://public.example",
        "https://example.com:0",
        "https://example.com:99999",
        "https://example.com:*",
        "https://example.com\\private",
        123,
    ],
)
def test_browser_policy_rejects_broad_or_ambiguous_origins_without_echo(monkeypatch, value):
    monkeypatch.setenv(policy.VARIABLE, json.dumps([value]))
    with pytest.raises(ValueError) as error:
        policy.content_security_policy()
    assert str(error.value) == policy.INVALID


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "private-invalid-json",
        "null",
        '"https://example.com"',
        '["https://example.com",' + '"https://example.com",' * 16 + '"https://example.com"]',
    ],
)
def test_invalid_configuration_does_not_fall_back_to_broad_access(monkeypatch, raw):
    monkeypatch.setenv(policy.VARIABLE, raw)
    with pytest.raises(ValueError, match="JSON list"):
        policy.configuration()
