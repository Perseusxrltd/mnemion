"""Release scan boundaries use actual archives without executing their contents."""

import io
import hashlib
import http.client
import json
import re
import socket
import ssl
import tarfile
import tomllib
import urllib.error
import zipfile
from contextlib import contextmanager

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
            "StartColumn": 17,
            "EndColumn": 31,
            "Entropy": 3.1933622,
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
    assert recorded["first_column"] == 17 and recorded["last_column"] == 31
    assert recorded["column_origin"] == "scanner_fragment"
    assert recorded["match_entropy"] == 3.1933622
    for private in (value.decode(), member, package.name, str(tmp_path)):
        assert private not in encoded
    assert result["matched_values_included"] is result["filenames_included"] is False


def test_rejection_summary_is_bounded_and_drops_unrecognized_rule_text(tmp_path):
    package = tmp_path / "input.txt"
    package.write_text("sample\n")
    observed = scan.scan_input([package], io.BytesIO())
    findings = [
        {
            "RuleID": "untrusted private/rule text",
            "StartLine": 2,
            "EndLine": 2,
            "StartColumn": "untrusted private/column",
            "EndColumn": -1,
            "Entropy": float("nan"),
        }
    ] * 200
    result = scan.summarize_findings(findings, observed["locations"])
    assert result["total"] == 200
    assert result["by_rule"] == {"unrecognized-rule": 200}
    assert len(result["locations"]) == 64 and result["locations_truncated"] is True
    assert "untrusted private/rule text" not in json.dumps(result)
    assert "untrusted private/column" not in json.dumps(result, allow_nan=False)
    assert all(
        "first_column" not in row and "match_entropy" not in row for row in result["locations"]
    )


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


def temporary_http(status):
    return urllib.error.HTTPError(
        "https://private.invalid/secret",
        status,
        "private-error-sentinel",
        {},
        io.BytesIO(b"private-body"),
    )


@pytest.mark.parametrize(
    "failure",
    [
        *[temporary_http(status) for status in (429, 500, 502, 503, 504)],
        TimeoutError("private-error-sentinel"),
        urllib.error.URLError(TimeoutError("private-error-sentinel")),
        ConnectionResetError("private-error-sentinel"),
        socket.gaierror("private-error-sentinel"),
        http.client.IncompleteRead(b"private-body"),
    ],
)
def test_scanner_retries_only_its_transient_download_once(monkeypatch, failure):
    name, payload = "linux_x64.tar.gz", b"pinned-scanner-fixture"
    monkeypatch.setitem(scan.ARCHIVES, name, hashlib.sha256(payload).hexdigest())
    calls, pauses = [], []

    def opened(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) == 1:
            raise failure
        return io.BytesIO(payload)

    monkeypatch.setattr(scan.urllib.request, "urlopen", opened)
    monkeypatch.setattr(scan.time, "sleep", pauses.append)
    assert scan.download_archive(name) == payload
    assert len(calls) == 2 and pauses == [2]
    assert all(0 < timeout <= 30 for _, timeout in calls)
    assert (
        calls[0][0]
        == calls[1][0]
        == (
            f"https://github.com/gitleaks/gitleaks/releases/download/v{scan.VERSION}/"
            f"gitleaks_{scan.VERSION}_{name}"
        )
    )


@pytest.mark.parametrize(
    "failure,code",
    [
        (temporary_http(401), "download_http"),
        (temporary_http(403), "download_http"),
        (temporary_http(404), "download_http"),
        (ssl.SSLCertVerificationError("private-error-sentinel"), "tls_error"),
        (urllib.error.URLError(ssl.SSLError("private-error-sentinel")), "tls_error"),
        (urllib.error.URLError("private-error-sentinel"), "unexpected_error"),
    ],
)
def test_scanner_refuses_nontransient_downloads_without_raw_error_text(monkeypatch, failure, code):
    calls = []

    def opened(*args, **kwargs):
        calls.append(True)
        raise failure

    monkeypatch.setattr(scan.urllib.request, "urlopen", opened)
    monkeypatch.setattr(scan.time, "sleep", lambda _: pytest.fail("Permanent failure retried"))
    with pytest.raises(scan.ScanError) as refused:
        scan.download_archive("linux_x64.tar.gz")
    assert len(calls) == 1
    assert refused.value.failure["code"] == code
    assert refused.value.failure["attempts"] == 1
    public = str(refused.value) + json.dumps(refused.value.failure)
    assert not any(
        value in public for value in ["private-error-sentinel", "private.invalid", "private-body"]
    )


def test_scanner_download_retry_exhaustion_keeps_no_partial_cache(tmp_path, monkeypatch):
    calls, pauses = [], []
    monkeypatch.setattr(scan, "archive_name", lambda: "linux_x64.tar.gz")

    def opened(*args, **kwargs):
        calls.append(True)
        raise temporary_http(503)

    monkeypatch.setattr(scan.urllib.request, "urlopen", opened)
    monkeypatch.setattr(scan.time, "sleep", pauses.append)
    with pytest.raises(scan.ScanError) as refused:
        with scan.scanner(tmp_path):
            pytest.fail("An incomplete scanner download was executed")
    assert refused.value.failure == {"code": "download_http", "http_status": 503, "attempts": 2}
    assert calls == [True, True] and pauses == [2]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("oversized", [False, True])
def test_download_size_and_integrity_failures_are_never_retried(monkeypatch, oversized):
    calls = []
    if oversized:
        monkeypatch.setattr(scan, "MAX_DOWNLOAD", 4)

    def opened(*args, **kwargs):
        calls.append(True)
        return io.BytesIO(b"unverified-scanner")

    monkeypatch.setattr(scan.urllib.request, "urlopen", opened)
    monkeypatch.setattr(scan.time, "sleep", lambda _: pytest.fail("Integrity failure retried"))
    with pytest.raises(scan.ScanError) as refused:
        scan.download_archive("linux_x64.tar.gz")
    assert len(calls) == 1
    assert refused.value.failure["code"] == (
        "download_oversized" if oversized else "download_integrity"
    )


def test_late_download_completion_cannot_extend_the_retry_window(monkeypatch):
    now = [0]

    class Late(io.BytesIO):
        def read1(self, size):
            now[0] = scan.DOWNLOAD_SECONDS + 1
            return super().read1(size)

    monkeypatch.setattr(scan.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(scan.urllib.request, "urlopen", lambda *a, **k: Late(b""))
    monkeypatch.setattr(scan.time, "sleep", lambda _: pytest.fail("Expired window retried"))
    with pytest.raises(scan.ScanError) as refused:
        scan.download_archive("linux_x64.tar.gz")
    assert refused.value.failure == {"code": "timeout", "attempts": 1}


def test_scan_initialization_failure_records_a_safe_stage_and_stays_closed(tmp_path, monkeypatch):
    (tmp_path / ".gitleaks.toml").write_text("fixture-rules")
    source = tmp_path / "sample.txt"
    source.write_text("fixture-source")
    output = tmp_path / "result.json"

    @contextmanager
    def denied(_cache):
        raise PermissionError("private-error-sentinel")
        yield  # pragma: no cover

    monkeypatch.setattr(scan, "scanner", denied)
    with pytest.raises(scan.ScanError) as refused:
        scan.scan(tmp_path, [source], output, tmp_path / "cache")
    record = json.loads(output.read_text())
    assert record["passed"] is False and "scanner" not in record
    assert record["failure"] == {"stage": "scanner_initialization", "code": "permission_denied"}
    assert "private-error-sentinel" not in str(refused.value) + output.read_text()


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


def test_electron_wasm_exception_is_one_exact_verified_public_fragment():
    config = tomllib.loads((scan.ROOT / ".gitleaks.toml").read_text())
    exception = next(
        item
        for item in config["allowlists"]
        if "Electron 44.9.3 WebAssembly" in item["description"]
    )
    value = scan.ELECTRON_WASM_FRAGMENT
    assert (
        hashlib.sha256(value.encode()).hexdigest()
        == "0503a3e3ff318b5b861741387a30b3772a1678ec1d26bf9524df4dc773eb3f61"
    )
    assert exception["regexTarget"] == "secret"
    assert exception["regexes"] == ["^" + re.escape(value) + "$"]
    for index in range(len(value)):
        replacement = "A" if value[index] != "A" else "B"
        assert not re.fullmatch(
            exception["regexes"][0], value[:index] + replacement + value[index + 1 :]
        )
    for other in (value[:-1], value + "A", "A" + value, value + ";token=another-value"):
        assert not re.fullmatch(exception["regexes"][0], other)


@pytest.mark.parametrize("application_findings", [2, 3, 4, 5, 6])
def test_canary_requires_binary_archive_annotation_and_encoded_key_detection(
    tmp_path, monkeypatch, application_findings
):
    def scanned(_executable, _rules, _paths, evidence):
        evidence.mkdir()
        findings = [{"RuleID": "mnemion-application-or-backup-key"}] * application_findings
        findings.append({"RuleID": "mnemion-vault-key"})
        findings.extend([{"RuleID": "square-access-token"}] * 2)
        (evidence / "0.private.json").write_text(json.dumps(findings))
        raise scan.ScanError("Fixture credential detection")

    monkeypatch.setattr(scan, "run_scanner", scanned)
    if application_findings < 6:
        with pytest.raises(scan.ScanError, match="every synthetic key placement"):
            scan.canary(None, None, tmp_path)
    else:
        scan.canary(None, None, tmp_path)


@pytest.mark.parametrize("square_findings", [0, 1])
def test_canary_requires_square_and_nearby_fragment_detection(
    tmp_path, monkeypatch, square_findings
):
    def scanned(_executable, _rules, _paths, evidence):
        evidence.mkdir()
        findings = [{"RuleID": "mnemion-application-or-backup-key"}] * 6
        findings.append({"RuleID": "mnemion-vault-key"})
        findings.extend([{"RuleID": "square-access-token"}] * square_findings)
        (evidence / "0.private.json").write_text(json.dumps(findings))
        raise scan.ScanError("Fixture credential detection")

    monkeypatch.setattr(scan, "run_scanner", scanned)
    with pytest.raises(scan.ScanError, match="every synthetic key placement"):
        scan.canary(None, None, tmp_path)
