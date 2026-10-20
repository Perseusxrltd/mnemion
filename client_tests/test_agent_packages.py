"""Exported native packages contain the chosen endpoint and no application identity."""

import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from mnemion import agent_packages as packages

ENDPOINT = "https://memory.example.test/mcp"


@pytest.mark.parametrize("provider", packages.PROVIDERS)
def test_packages_are_bounded_deterministic_and_use_canonical_perseus_branding(provider):
    result = packages.build(provider, ENDPOINT)
    raw = base64.b64decode(result["content_base64"], validate=True)
    assert len(raw) < 128 * 1024
    assert hashlib.sha256(raw).hexdigest() == result["sha256"]
    assert packages.build(provider, ENDPOINT) == result
    assert result["author"] == "Perseus XR" and result["contains_credentials"] is False
    with ZipFile(BytesIO(raw)) as archive:
        assert all(
            not Path(name).is_absolute() and ".." not in Path(name).parts
            for name in archive.namelist()
        )
        assert ".app.json" not in archive.namelist()
        assert (
            archive.read("assets/icon.png")
            == (Path(__file__).parents[1] / "studio/frontend/public/icon.png").read_bytes()
        )
        card = json.loads(archive.read("connection.json"))
        assert card["mcp_url"] == ENDPOINT and card["author"] == "Perseus XR"
        assert not {
            "client_secret",
            "api_key",
            "password",
            "access_token",
            "client_id",
        }.intersection(card)
        if provider == "openai":
            manifest = json.loads(archive.read("plugin.json"))
            assert manifest["author"]["name"] == "Perseus XR"
            assert (
                manifest["extensions"]["com.openai"]["interface"]["developerName"] == "Perseus XR"
            )
            assert json.loads(archive.read("mcp.json"))["mcpServers"]["mnemion"] == {
                "type": "streamable-http",
                "url": ENDPOINT,
            }
        elif provider in {"claude", "grok-build"}:
            manifest = json.loads(archive.read(".claude-plugin/plugin.json"))
            assert manifest["author"]["name"] == "Perseus XR"
            assert manifest["mcpServers"]["mnemion"] == {"type": "http", "url": ENDPOINT}
        elif provider == "hermes":
            assert yaml.safe_load(archive.read("config.yaml"))["mcp_servers"]["mnemion"] == {
                "url": ENDPOINT,
                "auth": "oauth",
            }
        elif provider == "openclaw":
            assert json.loads(archive.read("openclaw.json"))["mcp"]["servers"]["mnemion"] == {
                "url": ENDPOINT,
                "transport": "streamable-http",
                "auth": "oauth",
            }
        else:
            assert result["kind"] == "guide"


@pytest.mark.parametrize(
    "url",
    [
        "http://memory.example.test/mcp",
        "https://owner:secret@memory.example.test/mcp",
        ENDPOINT + "?access_token=private",
        ENDPOINT + "#private",
        ENDPOINT + "\n",
        "https://memory.example.test\\@other.test/mcp",
        "https://memory.example.test:bad/mcp",
        "https://memory.example.test/<script>",
        "",
        "https://" + "x" * 2048,
    ],
)
def test_credentials_and_unsafe_addresses_are_rejected_without_echoing_values(url):
    with pytest.raises(ValueError) as failure:
        packages.build("openai", url)
    assert "owner:secret" not in str(failure.value) and "access_token" not in str(failure.value)


def test_cli_writes_one_private_package_and_never_replaces_an_existing_file(tmp_path, capsys):
    output = tmp_path / "package.zip"
    arguments = ["--provider", "claude", "--mcp-url", ENDPOINT, "--output", str(output)]
    assert packages.main(arguments) == 0
    receipt = json.loads(capsys.readouterr().out)
    original = output.read_bytes()
    assert receipt["sha256"] == hashlib.sha256(original).hexdigest()
    assert "content_base64" not in receipt
    assert packages.main(arguments) == 2
    assert output.read_bytes() == original
    assert packages.main(["--catalog"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert len(catalog["providers"]) == 6
