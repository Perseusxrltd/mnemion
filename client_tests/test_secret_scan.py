"""Release scan boundaries use actual archives without executing their contents."""

import io
import hashlib
import json
import re
import tarfile
import tomllib
import zipfile

import pytest

from deploy import secret_scan as scan


def zipped(name, content):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, content)
    return stream.getvalue()


def test_nested_wheels_and_normally_excluded_names_are_inspected(tmp_path):
    package = tmp_path / "release.zip"
    package.write_bytes(zipped("nested.whl", zipped("package-lock.json", b"private-canary")))
    ordinary = tmp_path / "config.bin"
    ordinary.write_bytes(b"\x7fELF\x02\x01\x01\x00\nprivate-file-canary")
    output = io.BytesIO()
    report = scan.scan_input([ordinary, package], output)
    content = output.read()
    assert b"private-canary" in content
    assert ordinary.read_bytes() in content
    assert content.splitlines()[0].isascii()
    assert report["locations"][0]["first_line"] == 2
    assert any(
        item["member"].endswith("!nested.whl!package-lock.json") for item in report["locations"]
    )


def test_rejection_summary_identifies_asset_without_values_or_filenames(tmp_path):
    package = tmp_path / "private-file-name.whl"
    member = "private-archive-name.txt"
    value = b"confidential-value-must-not-enter-rejection-evidence"
    package.write_bytes(zipped(member, value))
    observed = scan.scan_input([package], io.BytesIO())
    location = next(item for item in observed["locations"] if item["member"].endswith(member))
    findings = [
        {
            "RuleID": "generic-api-key",
            "StartLine": location["first_line"],
            "EndLine": location["last_line"],
            "Secret": value.decode(),
            "Match": value.decode(),
            "File": str(package),
            "Description": member,
        }
    ]
    result = scan.summarize_findings(findings, observed["locations"])
    encoded = json.dumps(result)
    assert result["total"] == 1 and result["by_rule"] == {"generic-api-key": 1}
    assert len(result["locations"]) == 1
    recorded = result["locations"][0]
    assert recorded["input_sha256"] == hashlib.sha256(package.read_bytes()).hexdigest()
    assert recorded["member_path_sha256"] == hashlib.sha256(("!" + member).encode()).hexdigest()
    assert recorded["first_line"] == recorded["last_line"] == 1
    for private in (value.decode(), member, package.name, str(tmp_path)):
        assert private not in encoded
    assert result["matched_values_included"] is result["filenames_included"] is False


def test_rejection_summary_is_bounded_and_drops_unrecognized_rule_text(tmp_path):
    package = tmp_path / "input.txt"
    package.write_text("sample\n")
    observed = scan.scan_input([package], io.BytesIO())
    findings = [{"RuleID": "untrusted private/rule text", "StartLine": 2, "EndLine": 2}] * 200
    result = scan.summarize_findings(findings, observed["locations"])
    assert result["total"] == 200
    assert result["by_rule"] == {"unrecognized-rule": 200}
    assert len(result["locations"]) == 64 and result["locations_truncated"] is True
    assert "untrusted private/rule text" not in json.dumps(result)


def test_archive_expansion_and_depth_limits_fail_instead_of_skipping(tmp_path, monkeypatch):
    package = tmp_path / "large.whl"
    package.write_bytes(zipped("text.txt", b"x" * 1000))
    monkeypatch.setattr(scan, "MAX_EXPANSION", 500)
    with pytest.raises(scan.ScanError, match="oversized|budget"):
        scan.scan_input([package], io.BytesIO())
    monkeypatch.setattr(scan, "MAX_EXPANSION", 100000)
    content = b"private-nested-canary"
    for _ in range(6):
        content = zipped("nested.whl", content)
    package.write_bytes(content)
    with pytest.raises(scan.ScanError, match="depth budget"):
        scan.scan_input([package], io.BytesIO())


def test_archive_links_never_read_host_files(tmp_path):
    private = tmp_path / "private-host-data"
    private.write_bytes(b"host-file-content-must-never-be-read")
    archive = tmp_path / "links.tgz"
    with tarfile.open(archive, "w:gz") as package:
        entry = tarfile.TarInfo("../outside")
        entry.type, entry.linkname = tarfile.SYMTYPE, str(private)
        package.addfile(entry)
    output = io.BytesIO()
    scan.scan_input([archive], output)
    content = output.read()
    assert str(private).encode() in content
    assert private.read_bytes() not in content


def test_changed_scanner_cache_is_rejected_before_execution(tmp_path, monkeypatch):
    name = "linux_x64.tar.gz"
    monkeypatch.setattr(scan, "archive_name", lambda: name)
    (tmp_path / f"gitleaks_{scan.VERSION}_{name}").write_bytes(b"unverified-scanner")
    monkeypatch.setattr(
        scan.subprocess, "run", lambda *a, **k: pytest.fail("Unverified scanner executed")
    )
    with pytest.raises(scan.ScanError, match="pinned digest"):
        with scan.scanner(tmp_path):
            pytest.fail("Invalid scanner accepted")


def test_scanner_archive_rejects_linked_executable():
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        entry = tarfile.TarInfo("gitleaks")
        entry.type, entry.linkname = tarfile.SYMTYPE, "/unrelated/program"
        archive.addfile(entry)
    with pytest.raises(scan.ScanError, match="regular file"):
        scan.executable_bytes(output.getvalue(), "linux_x64.tar.gz")


def test_existing_exact_bounded_reader_exception_keeps_its_narrow_scope():
    config = tomllib.loads((scan.ROOT / ".gitleaks.toml").read_text())
    pattern = next(item for item in config["allowlists"] if item["regexTarget"] == "line")[
        "regexes"
    ][0]
    template = "    _read_json(selected.{name}, max_bytes={limit} * 1024 * 1024),"
    assert re.fullmatch(pattern, template.format(name="credentials", limit=16))
    assert not re.fullmatch(pattern, template.format(name="credentials", limit=32))


def test_type_annotation_exception_cannot_hide_a_second_value_or_statement():
    config = tomllib.loads((scan.ROOT / ".gitleaks.toml").read_text())
    exception = next(item for item in config["allowlists"] if "HPKE stub" in item["description"])
    assert exception["regexTarget"] == "line"
    pattern = exception["regexes"][0]
    annotation = "    private_key: " + "x25519.X25519PrivateKey"
    assert re.fullmatch(pattern, annotation)
    assert re.fullmatch(pattern, annotation + "\n")
    assert re.fullmatch(pattern, annotation + "\r\n")
    for suffix in ("; token = confidential-value", " = confidential-value", "\nother_line"):
        assert not re.fullmatch(pattern, annotation + suffix)
    assert not re.fullmatch(pattern, annotation.replace("X25519PrivateKey", "ActualPrivateValue"))


def test_migration_exceptions_are_only_exact_digests_of_public_source_files():
    config = tomllib.loads((scan.ROOT / ".gitleaks.toml").read_text())
    exception = next(
        item for item in config["allowlists"] if "migration SHA-256" in item["description"]
    )
    assert exception["regexTarget"] == "secret"
    names = ("013_oauth_bindings.sql", "016_hosted_oauth.sql", "020_secrets_vault.sql")
    expected = {
        "^"
        + hashlib.sha256((scan.ROOT / "mnemion/service/migrations" / name).read_bytes()).hexdigest()
        + "$"
        for name in names
    }
    assert set(exception["regexes"]) == expected
    assert not any(re.fullmatch(pattern, "a" * 64) for pattern in expected)


def test_fips_exception_is_only_the_public_default_and_exact_observed_fragment():
    config = tomllib.loads((scan.ROOT / ".gitleaks.toml").read_text())
    exception = next(
        item for item in config["allowlists"] if "FIPS module-integrity" in item["description"]
    )
    expected = hashlib.sha256(b"holy hand grenade of antioch").hexdigest()
    assert exception["regexTarget"] == "secret"
    assert exception["regexes"] == ["^" + expected + "$", "^" + expected[:38] + "$"]
    refused = [expected[:length] for length in range(1, 64) if length != 38]
    refused += ["a" * 64, expected + "0", expected + ";token=another-value"]
    refused += [expected[:38] + "0", expected[:38] + ";token=another-value"]
    for value in refused:
        assert not any(re.fullmatch(pattern, value) for pattern in exception["regexes"])


@pytest.mark.parametrize("application_findings", [2, 3, 4, 5, 6])
def test_canary_requires_binary_archive_annotation_and_encoded_key_detection(
    tmp_path, monkeypatch, application_findings
):
    def scanned(_executable, _rules, _paths, evidence):
        evidence.mkdir()
        findings = [{"RuleID": "mnemion-application-or-backup-key"}] * application_findings
        findings.append({"RuleID": "mnemion-vault-key"})
        (evidence / "0.private.json").write_text(json.dumps(findings))
        raise scan.ScanError("Fixture credential detection")

    monkeypatch.setattr(scan, "run_scanner", scanned)
    if application_findings < 6:
        with pytest.raises(scan.ScanError, match="every synthetic key placement"):
            scan.canary(None, None, tmp_path)
    else:
        scan.canary(None, None, tmp_path)
