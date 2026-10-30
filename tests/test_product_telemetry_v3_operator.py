"""Dedicated v3 serving and the private maintainer HTML export.

These checks stay on the local collector and the export command. They do not
open a network collector, start a host, or treat a synthetic week as fleet evidence.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

from mnemion.product_telemetry.aggregate_v3 import NUMERATOR, AggregateWindow, validate
from mnemion.product_telemetry.collector_v3 import CollectorV3
from mnemion.product_telemetry.maintainer_v3 import _page, main, render
from mnemion.product_telemetry.publication_v3 import ReportStore
from mnemion.product_telemetry.reporting import reporting_week
from mnemion.product_telemetry.server import (
    ConfigurationError,
    MetadataBoundary,
    _selected_application,
    main as serve_main,
)
from mnemion.product_telemetry.wire_v3 import METRICS, METRIC_BY_ID, encode

ROOT = Path(__file__).resolve().parents[1]
CANARY = b"PRIVATE_REQUEST_CANARY"
WEEK_ZERO = 345600


def stamp(week: int) -> int:
    return WEEK_ZERO + week * 604800


def stop(limit: int) -> int:
    return limit - 1


def packet() -> bytes:
    return encode("release", [2] * len(METRICS), release=(4, 46, 53))


def minus_one(limit: int) -> int:
    """One discrete-Laplace draw of -1, then zeros. The second geometric continues once."""
    minus_one.calls += 1
    if minus_one.calls == 2:
        assert limit == 17381 or limit > NUMERATOR
        return 0
    return limit - 1


minus_one.calls = 0


def island(page: str) -> dict:
    marker = '<script type="application/json" id="fleet-report">'
    start = page.index(marker) + len(marker)
    body = page[start : page.index("</script>", start)]
    assert "<" not in body
    return json.loads(body)


def test_boundary_scheduler_prunes_quiet_week_failure_notices():
    clock = {"now": stamp(2908) + 604800 - 0.02}
    app = CollectorV3(lambda _result: None, clock=lambda: clock["now"])
    app._publication_failures = [
        {"window_week": 2899, "state": "publication_failed"},
        {"window_week": 2901, "state": "publication_failed"},
        {"window_week": 2908, "state": "publication_failed"},
    ]

    async def once():
        task = asyncio.create_task(app._boundaries())
        await asyncio.sleep(0.25)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(once())
    assert app._publication_failures == [{"window_week": 2901, "state": "publication_failed"}]


def test_metadata_boundary_keeps_only_the_selected_route():
    seen = {}

    async def app(scope, _receive, _send):
        seen.update(scope)

    asyncio.run(
        MetadataBoundary(app, route="/v3/report")(
            {
                "type": "http",
                "method": "POST",
                "path": "/v3/report",
                "query_string": CANARY,
                "headers": [(b"authorization", CANARY), (b"x-request-id", CANARY)],
                "client": ("192.0.2.7", 10000),
                "server": ("192.0.2.8", 8443),
            },
            None,
            None,
        )
    )
    assert seen["path"] == "/v3/report"
    assert seen["query_string"] == b"?"
    assert seen["headers"] == []
    assert seen["client"] is seen["server"] is None
    assert CANARY.decode() not in repr(seen)

    asyncio.run(
        MetadataBoundary(app, route="/v3/report")(
            {
                "type": "http",
                "method": "POST",
                "path": "/v1/report",
                "query_string": b"",
                "headers": [],
            },
            None,
            None,
        )
    )
    assert seen["path"] == "/"
    with pytest.raises(ConfigurationError):
        MetadataBoundary(app, route="/v3/report?week=1")


def _service_settings(text: str) -> dict[str, list[str]]:
    section = None
    found: dict[str, list[str]] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "Service" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        found.setdefault(key.strip(), []).append(value.strip())
    return found


def _environment(assignments: list[str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for assignment in assignments:
        if assignment == "":
            merged.clear()
            continue
        for token in assignment.split():
            name, separator, value = token.partition("=")
            assert separator == "="
            merged[name] = value
    return merged


def test_shipped_service_mode_contract_preserves_both_stores(tmp_path, capsys):
    """Check the shipped template contract, not a running systemd installation."""
    unit = _service_settings((ROOT / "deploy/collector/mnemion-telemetry.service").read_text())
    drop_in = _service_settings(
        (ROOT / "deploy/collector/mnemion-telemetry.service.d/v3.conf").read_text()
    )
    assert set(drop_in) == {"Environment"}
    assert drop_in["Environment"] == ["MNEMION_TELEMETRY_MODE=v3"]
    command = unit["ExecStart"]
    assert len(command) == 1
    parts = command[0].split()
    assert parts.count("--mode") == 1
    assert parts[parts.index("--mode") + 1] == "${MNEMION_TELEMETRY_MODE}"
    assert "MNEMION_TELEMETRY_MODE" not in unit["UnsetEnvironment"][0]
    shipped = _environment(unit["Environment"])
    assert shipped["MNEMION_TELEMETRY_MODE"] == "legacy"
    assert shipped["PYTHONNOUSERSITE"] == "1"
    assert shipped["PYTHONDONTWRITEBYTECODE"] == "1"
    selected = _environment([*unit["Environment"], *drop_in["Environment"]])
    assert selected["MNEMION_TELEMETRY_MODE"] == "v3"
    assert selected["PYTHONNOUSERSITE"] == "1"
    assert selected["PYTHONDONTWRITEBYTECODE"] == "1"

    legacy_root = tmp_path / "legacy"
    legacy = _selected_application(shipped["MNEMION_TELEMETRY_MODE"], legacy_root)
    assert legacy.route == "/v1/report"
    assert (legacy_root / "reports.sqlite3").is_file()
    assert not (legacy_root / "reports-v3.sqlite3").exists()
    current = _selected_application(selected["MNEMION_TELEMETRY_MODE"], legacy_root)
    assert current.route == "/v3/report"
    assert type(current.app) is CollectorV3
    assert (legacy_root / "reports-v3.sqlite3").is_file()
    assert (legacy_root / "reports.sqlite3").is_file()
    restored = _selected_application(shipped["MNEMION_TELEMETRY_MODE"], legacy_root)
    assert restored.route == "/v1/report"
    assert (legacy_root / "reports-v3.sqlite3").is_file()

    rejected = "PRIVATE_MODE_CANARY"
    state = tmp_path / "unused"
    assert (
        serve_main(
            [
                "serve",
                "--mode",
                rejected,
                "--state",
                str(state),
                "--certificate",
                str(tmp_path / "certificate.pem"),
                "--private-key",
                str(tmp_path / "private-key.pem"),
            ]
        )
        == 2
    )
    leaked = capsys.readouterr()
    assert leaked.out == ""
    assert json.loads(leaked.err) == {"error": "telemetry_collector_configuration_invalid"}
    assert rejected not in leaked.err
    assert not state.exists()
    assert (legacy_root / "reports-v3.sqlite3").is_file()


def test_modes_mount_the_real_collector_and_an_isolated_store(tmp_path):
    legacy_root = tmp_path / "legacy"
    legacy = _selected_application("legacy", legacy_root)
    assert legacy.route == "/v1/report"
    assert type(legacy.app).__name__ == "Collector"
    assert (legacy_root / "reports.sqlite3").is_file()
    assert not (legacy_root / "reports-v3.sqlite3").exists()

    v3_root = tmp_path / "v3"
    selected = _selected_application("v3", v3_root)
    assert selected.route == "/v3/report"
    assert type(selected.app) is CollectorV3
    assert (v3_root / "reports-v3.sqlite3").is_file()
    assert not (v3_root / "reports.sqlite3").exists()
    with pytest.raises(ConfigurationError):
        _selected_application("v4", tmp_path / "unknown")


def test_operator_errors_do_not_echo_or_create_a_store(tmp_path, capsys):
    secret = tmp_path / "credential-looking-directory"
    assert main(["--state", str(secret), "--format", "html"]) == 2
    assert not secret.exists()
    leaked = capsys.readouterr()
    assert "credential-looking-directory" not in leaked.out + leaked.err
    assert leaked.out == '{"ok": false, "error": "telemetry_v3_export_rejected"}\n'

    token = "not-a-real-format"
    assert main(["--state", str(secret), "--format", token]) == 2
    leaked = capsys.readouterr()
    assert token not in leaked.out + leaked.err
    assert str(secret) not in leaked.out + leaked.err

    assert (
        serve_main(
            [
                "serve",
                "--mode",
                token,
                "--state",
                str(secret),
                "--certificate",
                str(secret / "cert.pem"),
                "--private-key",
                str(secret / "key.pem"),
            ]
        )
        == 2
    )
    leaked = capsys.readouterr()
    assert leaked.err == '{"error":"telemetry_collector_configuration_invalid"}\n'
    assert token not in leaked.err
    assert "credential-looking-directory" not in leaked.err
    assert not secret.exists()


def test_html_export_keeps_json_csv_legend_and_escapes_script(tmp_path, capsys, monkeypatch):
    current = reporting_week(time.time())

    def clock() -> int:
        return stamp(current)

    store = ReportStore(tmp_path, clock=clock)
    peaked = AggregateWindow(current - 1)
    for _ in range(2000):
        assert peaked.contribute(packet())
    peaked_report = peaked.seal(stop)
    minus_one.calls = 0
    negative = AggregateWindow(current - 2).seal(minus_one)
    assert negative["global"]["denominator"] < 0
    store(peaked_report)
    store(negative)
    store.record_publication_failure(current - 3)

    json_text = render(store.reports(), "json", store.publication_failures())
    csv_text = render(store.reports(), "csv", store.publication_failures())
    html = render(store.reports(), "html", store.publication_failures())
    document = json.loads(json_text)
    assert document["summary"]["report_count"] == 2
    assert document["summary"]["publication_failures"][0]["state"] == "publication_failed"
    assert csv_text.splitlines()[0].startswith(
        "record,ordinary_privacy_settings_contain_fleet_data"
    )
    assert csv_text.splitlines()[1].endswith("," + str(current - 3))
    assert html.startswith("<!DOCTYPE html>")
    assert "innerHTML" not in html
    assert "fonts.googleapis" not in html and "cdn" not in html.lower()
    assert "#02050d" in html and "#f2ead9" in html and "#c49a55" in html

    view = island(html)
    assert view["reports_are_not_unique_people"] is True
    assert view["ordinary_privacy_settings_contain_fleet_data"] is False
    assert [item["window_week"] for item in view["publication_failures"]] == [current - 3]
    assert len(view["weeks"]) == 2
    week = next(item for item in view["weeks"] if item["week"] == current - 1)
    assert set(week) >= {"release", "os", "remainder", "domain_metrics"}
    assert "release_os" not in week
    release = next(row for row in week["release"] if row["id"] == "4.46.53")
    assert len(release["metrics"]) == 19
    assert any(
        metric["quantiles"]["p50"]["state"] == "bucket_bounds"
        for metric in release["metrics"]
        if "quantiles" in metric
    )
    negative_week = next(item for item in view["weeks"] if item["week"] == current - 2)
    assert negative_week["domain_denominator"] < 0
    assert any(
        metric["quantiles"]["p50"]["state"] == "insufficient_precision"
        for metric in negative_week["domain_metrics"]
        if "quantiles" in metric
    )
    saved = week["frozen_legend"]
    latency = next(item for item in saved if item["id"] == "latency_ms")
    live = METRIC_BY_ID["latency_ms"]
    monkeypatch.setitem(live, "upper_bounds", [bound + 1 for bound in live["upper_bounds"]])
    again = island(render([peaked_report], "html"))
    again_latency = next(
        metric
        for metric in next(item for item in again["weeks"] if item["week"] == current - 1)[
            "release"
        ]
        if metric["id"] == "4.46.53"
        for metric in metric["metrics"]
        if metric["id"] == "latency_ms"
    )
    assert again_latency["buckets"][2]["label"] == f"0-{latency['upper_bounds'][0]}"
    assert again_latency["buckets"][2]["label"] != f"0-{live['upper_bounds'][0]}"

    hostile = _page({"legend": "</script><script>alert(1)</script>", "amp": 'a&b"c'})
    parsed = island(hostile)
    assert parsed["legend"] == "</script><script>alert(1)</script>"
    assert "<script>alert" not in hostile
    assert hostile.count("</script>") == 2

    assert main(["--state", str(tmp_path), "--format", "html"]) == 0
    exported = capsys.readouterr().out
    exported_view = island(exported)
    assert exported_view["publication_failures"] == [
        {"window_week": current - 3, "state": "publication_failed"}
    ]
    assert exported_view["weeks"]

    bare = tmp_path / "empty-store"
    ReportStore(bare, clock=clock)
    assert main(["--state", str(bare), "--format", "html"]) == 0
    empty = capsys.readouterr().out
    assert "No closed weeks" in empty
    assert island(empty)["weeks"] == []


def _certificate(folder: Path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    certificate, private_key = folder / "certificate.pem", folder / "key.pem"
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private_key.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_key.chmod(0o600)
    return certificate, private_key


def _exchange(context, address, port, payload: bytes) -> bytes:
    raw = socket.create_connection((address, port), timeout=8)
    try:
        with context.wrap_socket(raw, server_hostname="localhost") as channel:
            channel.sendall(payload)
            received = bytearray()
            while part := channel.recv(2048):
                received.extend(part)
            assert CANARY not in received
            assert channel.version() == "TLSv1.3"
            return bytes(received)
    except BaseException:
        raw.close()
        raise


@contextmanager
def _listen(tmp_path: Path, mode: str | None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    certificate, private_key = _certificate(tmp_path)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    state = tmp_path / "state"
    stdout, stderr = tmp_path / "stdout", tmp_path / "stderr"
    context = ssl.create_default_context(cafile=certificate)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    command = [
        sys.executable,
        "-m",
        "mnemion.product_telemetry.server",
        "serve",
        "--state",
        str(state),
        "--bind",
        "127.0.0.1",
        "--port",
        str(port),
        "--certificate",
        str(certificate),
        "--private-key",
        str(private_key),
    ]
    if mode is not None:
        command[4:4] = ["--mode", mode]
    with stdout.open("wb") as out, stderr.open("wb") as err:
        child = subprocess.Popen(
            command,
            cwd=ROOT,
            env={**os.environ, "PYTHONNOUSERSITE": "1", "SSLKEYLOGFILE": str(tmp_path / "keylog")},
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
        )
        try:
            deadline = time.monotonic() + 8
            ready = (
                b"OPTIONS /v3/report HTTP/1.1\r\nHost: localhost\r\n\r\n"
                if mode == "v3"
                else (b"OPTIONS /v1/report HTTP/1.1\r\nHost: localhost\r\n\r\n")
            )
            while True:
                assert child.poll() is None, stderr.read_text()
                try:
                    assert _exchange(context, "127.0.0.1", port, ready).startswith(b"HTTP/1.1 204")
                    break
                except OSError:
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
            yield context, port, state, stdout, stderr
        finally:
            child.terminate()
            child.wait(timeout=8)
    assert not (tmp_path / "keylog").exists()
    assert stdout.read_bytes() == stderr.read_bytes() == b""


def test_local_tls_v3_accepts_its_packet_and_legacy_stays_default(tmp_path):
    body = packet()
    good = (
        b"POST /v3/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\nX-Request-ID: "
        + CANARY
        + b"\r\nAuthorization: "
        + CANARY
        + b"\r\n\r\n"
        + body
    )
    malformed = b"POST /v3/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: 25\r\n\r\n" + (
        b"\x00" * 25
    )
    wrong = (
        b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    queried = (
        b"POST /v3/report?" + CANARY + b" HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n"
    )
    with _listen(tmp_path / "v3", "v3") as (context, port, state, stdout, stderr):
        assert _exchange(context, "127.0.0.1", port, good).startswith(b"HTTP/1.1 204")
        assert _exchange(context, "127.0.0.1", port, malformed).startswith(b"HTTP/1.1 400")
        assert _exchange(context, "127.0.0.1", port, wrong).startswith(b"HTTP/1.1 404")
        assert _exchange(context, "127.0.0.1", port, queried).startswith(b"HTTP/1.1 404")
        stored = (state / "reports-v3.sqlite3").read_bytes()
        assert CANARY not in stored
        assert CANARY not in stdout.read_bytes() + stderr.read_bytes()
        assert not (state / "reports.sqlite3").exists()
    legacy_root = tmp_path / "legacy"
    with _listen(legacy_root, None) as (context, port, state, _stdout, _stderr):
        assert _exchange(
            context, "127.0.0.1", port, b"OPTIONS /v1/report HTTP/1.1\r\nHost: localhost\r\n\r\n"
        ).startswith(b"HTTP/1.1 204")
        assert _exchange(
            context, "127.0.0.1", port, b"OPTIONS /v3/report HTTP/1.1\r\nHost: localhost\r\n\r\n"
        ).startswith(b"HTTP/1.1 404")
        assert (state / "reports.sqlite3").is_file()
        assert not (state / "reports-v3.sqlite3").exists()


def _rejected(capsys) -> str:
    leaked = capsys.readouterr()
    assert "Traceback" not in leaked.out + leaked.err
    return leaked.out + leaked.err


def test_corrupt_or_locked_export_stays_a_fixed_error(tmp_path, capsys):
    corrupt = tmp_path / "credential-looking-store"
    ReportStore(corrupt)
    target = corrupt / "reports-v3.sqlite3"
    original = b"not-a-sqlite-database"
    target.write_bytes(original)
    assert main(["--state", str(corrupt), "--format", "json"]) == 2
    leaked = _rejected(capsys)
    assert leaked == '{"ok": false, "error": "telemetry_v3_export_rejected"}\n'
    assert "credential-looking-store" not in leaked
    assert target.read_bytes() == original

    locked = tmp_path / "busy-store"
    ReportStore(locked)
    database = locked / "reports-v3.sqlite3"
    before = database.read_bytes()
    held = sqlite3.connect(database, isolation_level=None)
    held.execute("BEGIN EXCLUSIVE")
    try:
        assert main(["--state", str(locked), "--format", "html"]) == 2
    finally:
        held.rollback()
        held.close()
    leaked = _rejected(capsys)
    assert leaked == '{"ok": false, "error": "telemetry_v3_export_rejected"}\n'
    assert "busy-store" not in leaked
    assert "database is locked" not in leaked
    assert database.read_bytes() == before
    assert main(["--state", str(locked), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["report_count"] == 0


def test_v3_serve_rejects_a_bad_store_without_replacing_it(tmp_path, capsys):
    root = tmp_path / "v3-bad-store"
    ReportStore(root)
    target = root / "reports-v3.sqlite3"
    original = b"not-a-sqlite-database"
    target.write_bytes(original)
    certificate, private_key = root / "certificate.pem", root / "key.pem"
    certificate.write_bytes(b"unused-certificate")
    private_key.write_bytes(b"unused-key")
    assert (
        serve_main(
            [
                "serve",
                "--mode",
                "v3",
                "--state",
                str(root),
                "--certificate",
                str(certificate),
                "--private-key",
                str(private_key),
            ]
        )
        == 2
    )
    leaked = _rejected(capsys)
    assert leaked == '{"error":"telemetry_collector_configuration_invalid"}\n'
    assert str(root) not in leaked
    assert target.read_bytes() == original

    busy = tmp_path / "v3-busy-store"
    ReportStore(busy)
    database = busy / "reports-v3.sqlite3"
    before = database.read_bytes()
    held = sqlite3.connect(database, isolation_level=None)
    held.execute("BEGIN EXCLUSIVE")
    try:
        assert (
            serve_main(
                [
                    "serve",
                    "--mode",
                    "v3",
                    "--state",
                    str(busy),
                    "--certificate",
                    str(certificate),
                    "--private-key",
                    str(private_key),
                ]
            )
            == 2
        )
    finally:
        held.rollback()
        held.close()
    leaked = _rejected(capsys)
    assert leaked == '{"error":"telemetry_collector_configuration_invalid"}\n'
    assert "database is locked" not in leaked
    assert database.read_bytes() == before


def test_category_names_follow_the_live_catalog(monkeypatch):
    report = validate(AggregateWindow(10).seal(stop))
    saved = next(item for item in report["domain"]["metric_legend"] if item["id"] == "outcome")
    assert saved == {"id": "outcome", "kind": "categories"}
    live = METRIC_BY_ID["outcome"]
    monkeypatch.setitem(live, "categories", ["renamed-success", *live["categories"][1:]])
    view = island(render([report], "html"))
    labels = next(
        metric["buckets"]
        for metric in view["weeks"][0]["domain_metrics"]
        if metric["id"] == "outcome"
    )
    assert labels[2]["label"] == "renamed-success"
    outcome = next(item for item in view["weeks"][0]["frozen_legend"] if item["id"] == "outcome")
    assert outcome == {"id": "outcome", "kind": "categories"}


_TREND_PAGE = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const marker = '<script type="application/json" id="fleet-report">';
const jsonStart = html.indexOf(marker) + marker.length;
const jsonEnd = html.indexOf("</script>", jsonStart);
const scriptStart = html.indexOf("<script>", jsonEnd) + "<script>".length;
const scriptEnd = html.indexOf("</script>", scriptStart);
const code = html.slice(scriptStart, scriptEnd);

function Element(tag) {
  this.tag = tag;
  this.children = [];
  this.attrs = {};
  this._text = "";
  this.className = "";
  this.style = {};
  this.hidden = false;
  this.disabled = false;
  this._value = "";
  this.checked = false;
  this.options = [];
  this.selectedIndex = -1;
  this.listeners = {};
  this.scope = "";
}
Object.defineProperty(Element.prototype, "textContent", {
  get() { return this._text; },
  set(value) { this._text = String(value); },
});
Object.defineProperty(Element.prototype, "value", {
  get() {
    if (this.tag === "SELECT" && this.selectedIndex >= 0 && this.options[this.selectedIndex]) {
      return this.options[this.selectedIndex].value;
    }
    return this._value;
  },
  set(value) {
    this._value = String(value);
    if (this.tag === "SELECT") {
      for (let index = 0; index < this.options.length; index += 1) {
        if (this.options[index].value === this._value) this.selectedIndex = index;
      }
    }
  },
});
Object.defineProperty(Element.prototype, "firstChild", {
  get() { return this.children[0] || null; },
});
Element.prototype.setAttribute = function (name, value) { this.attrs[name] = String(value); };
Element.prototype.appendChild = function (child) {
  this.children.push(child);
  if (this.tag === "SELECT") {
    this.options.push(child);
    if (this.selectedIndex < 0) this.selectedIndex = 0;
  }
  return child;
};
Element.prototype.removeChild = function (child) {
  this.children = this.children.filter((item) => item !== child);
  this.options = this.options.filter((item) => item !== child);
  if (this.selectedIndex >= this.options.length) this.selectedIndex = this.options.length - 1;
  return child;
};
Element.prototype.addEventListener = function (type, fn) {
  (this.listeners[type] ||= []).push(fn);
};
Element.prototype.dispatch = function (type) {
  (this.listeners[type] || []).forEach((fn) => fn());
};

const nodes = {};
["week", "cohort", "failures", "empty", "detail", "denominator", "trend", "metrics", "fleet-report"].forEach((id) => {
  nodes[id] = new Element(id === "week" || id === "cohort" ? "SELECT" : "DIV");
});
nodes["fleet-report"].textContent = html.slice(jsonStart, jsonEnd);
const radios = ["release", "os", "domain"].map((value) => {
  const node = new Element("INPUT");
  node.value = value;
  node.checked = value === "release";
  return node;
});
const document = {
  getElementById(id) { return nodes[id]; },
  querySelector(selector) {
    if (selector === 'input[name="axis"]:checked') return radios.find((node) => node.checked) || null;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === 'input[name="axis"]') return radios;
    return [];
  },
  createElement(tag) { return new Element(String(tag).toUpperCase()); },
  createElementNS(_ns, tag) { return new Element(tag); },
};
const vm = require("vm");
vm.runInNewContext(code, { document: document }, { timeout: 5000 });
const weekSel = nodes.week;
const cohortSel = nodes.cohort;
const initialWeek = weekSel.value;
weekSel.value = "10";
weekSel.dispatch("change");
cohortSel.value = "remainder";
cohortSel.dispatch("change");
const trendText = nodes.trend.children.map((node) => node.textContent).join("\n");
let points = "";
function walk(node) {
  if (node.attrs && node.attrs.points) points = node.attrs.points;
  node.children.forEach(walk);
}
walk(nodes.trend);
const headers = [];
function walkHeaders(node) {
  if (node.tag === "TH") headers.push(node.textContent);
  node.children.forEach(walkHeaders);
}
walkHeaders(nodes.trend);
cohortSel.value = "1";
cohortSel.dispatch("change");
const selectedOnOldWeek = cohortSel.options[cohortSel.selectedIndex].textContent;
weekSel.value = "12";
weekSel.dispatch("change");
const selectedAfterWeekChange = cohortSel.options[cohortSel.selectedIndex].textContent;
const afterIdentity = nodes.denominator.textContent;
process.stdout.write(JSON.stringify({
  initialWeek, points, trendText, headers, selectedOnOldWeek, selectedAfterWeekChange, afterIdentity
}));
"""


def test_remainder_trend_uses_the_same_member_set_and_week_positions(tmp_path):
    node = shutil.which("node") or "/usr/bin/node"
    assert Path(node).is_file()

    def week(number: int, members: list[str], denominator: int, releases: list[dict]) -> dict:
        return {
            "week": number,
            "frozen_legend": [],
            "report_unit": "anonymous_bounded_summary_not_a_person_or_installation",
            "comparisons": "separate_axes_in_one_week_not_a_joined_profile",
            "noise_uncertainty_is_not": "independent_user_sampling_or_causal_inference",
            "domain_label": "sum_of_noisy_full_domain",
            "domain_denominator": denominator,
            "domain_metrics": [],
            "release": releases,
            "os": [],
            "remainder": {
                "release": {
                    "ids": members,
                    "denominator": denominator,
                    "metrics": [],
                    "quantiles": "not_a_single_population",
                },
                "os": None,
            },
        }

    page = _page(
        {
            "surface": "private_maintainer_export",
            "ordinary_privacy_settings_contain_fleet_data": False,
            "reports_are_not_unique_people": True,
            "noise_is_not_a_population_or_causal_confidence_interval": True,
            "publication_failures": [],
            "weeks": [
                week(
                    10,
                    ["aa", "bb"],
                    3,
                    [
                        {"id": "4.46.53", "slot": 0, "denominator": 10, "metrics": []},
                        {"id": "unlisted", "slot": 1, "denominator": 11, "metrics": []},
                    ],
                ),
                week(
                    12,
                    ["aa", "cc"],
                    9,
                    [
                        {"id": "4.46.53", "slot": 0, "denominator": 10, "metrics": []},
                        {"id": "4.46.54", "slot": 1, "denominator": 77, "metrics": []},
                        {"id": "unlisted", "slot": 2, "denominator": 22, "metrics": []},
                    ],
                ),
                week(11, ["bb", "aa"], 4, []),
            ],
        }
    )
    html_path = tmp_path / "trend.html"
    script_path = tmp_path / "check-trend.js"
    html_path.write_text(page, encoding="utf-8")
    script_path.write_text(_TREND_PAGE, encoding="utf-8")
    ran = subprocess.run(
        [node, str(script_path), str(html_path)], capture_output=True, text=True, timeout=20
    )
    assert ran.returncode == 0, ran.stderr
    found = json.loads(ran.stdout)
    assert found["initialWeek"] == "12"
    assert found["points"].startswith("16.0,")
    assert "320.0," in found["points"]
    assert "624.0," not in found["points"]
    assert found["headers"] == ["Week 10", "Week 11"]
    assert "Member set: aa + bb" in found["trendText"]
    assert "different suppressed set" in found["trendText"]
    assert found["selectedOnOldWeek"] == "unlisted"
    assert found["selectedAfterWeekChange"] == "unlisted"
    assert found["afterIdentity"] == "unlisted noisy denominator 22. Not unique people."
    assert "4.46.54" not in found["afterIdentity"]


class _Body:
    def __init__(self, payload: bytes, url: str, status: int = 200):
        self._payload = payload
        self.status = status
        self._url = url

    def read(self, amount: int) -> bytes:
        block = self._payload[:amount]
        self._payload = self._payload[amount:]
        return block

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_v3_catalog_sync_is_scheduled_outside_the_collector(tmp_path, capsys, monkeypatch):
    """The timer is wired for v3. The collector does not fetch, and a bad body is not installed."""
    import urllib.request

    from mnemion.product_telemetry.release_catalog import (
        FILENAME,
        LOCAL_KEYS,
        SOURCE,
        CatalogError,
        main as catalog_main,
        sync_catalog,
    )

    drop_in = (ROOT / "deploy/collector/mnemion-telemetry.service.d/v3.conf").read_text()
    base = (ROOT / "deploy/collector/mnemion-telemetry.service").read_text()
    service = (ROOT / "deploy/collector/mnemion-telemetry-catalog.service").read_text()
    timer = (ROOT / "deploy/collector/mnemion-telemetry-catalog.timer").read_text()
    guide = (ROOT / "docs/implementation/anonymous-product-telemetry-collector.md").read_text()
    assert "Wants=mnemion-telemetry-catalog.timer" in drop_in
    assert "Environment=MNEMION_TELEMETRY_MODE=v3" in drop_in
    assert "ExecStart" not in drop_in
    assert "LoadCredential" not in drop_in
    assert "Environment=MNEMION_TELEMETRY_MODE=legacy" in base
    assert "SystemCallFilter=~connect bind" in base
    assert "LoadCredential=tls.pem:/etc/mnemion-telemetry/tls.pem" in base
    assert "mnemion-telemetry-catalog" not in base
    assert "LoadCredential" not in service
    assert "tls.pem" not in service
    assert "SystemCallFilter=~connect" not in service
    assert "--mode" not in service
    assert "release_catalog sync --state /var/lib/mnemion-telemetry" in service
    assert "User=mnemion-telemetry" in service
    assert "OnCalendar=daily" in timer
    assert "Persistent=true" in timer
    assert "RandomizedDelaySec=1h" in timer
    assert "Unit=mnemion-telemetry-catalog.service" in timer
    assert "mnemion-telemetry-catalog.timer" in guide
    assert "does not turn client collection on" in guide

    def refused(*_args, **_kwargs):
        raise AssertionError("collector must not fetch a catalog")

    monkeypatch.setattr(urllib.request, "urlopen", refused)
    selected = _selected_application("v3", tmp_path / "collector")
    assert selected.app._catalog_path == tmp_path / "collector" / FILENAME
    assert selected.app.catalog_adoption["state"] == "bundled"
    assert selected.app.catalog_adoption["reason"] == "missing"
    assert selected.app._window.contribute(packet())

    wire = json.loads((ROOT / "mnemion/product_telemetry/wire-v3.json").read_text())
    body = json.dumps(wire).encode()

    def opener(request, timeout):
        assert request.full_url == SOURCE
        assert request.get_header("Authorization") is None
        assert timeout == 15
        return _Body(body, SOURCE)

    destination = tmp_path / "state"
    destination.mkdir()
    written = sync_catalog(destination, now=1_700_000_000, opener=opener)
    saved = json.loads(written.read_text(encoding="utf-8"))
    assert set(saved) == LOCAL_KEYS
    assert saved["source"] == SOURCE
    assert saved["generated_at"] == 1_700_000_000
    assert saved["release_allowlist"] == wire["release_allowlist"]
    assert "metrics" not in saved
    assert b"packet" not in written.read_bytes()

    def bad_opener(request, timeout):
        assert request.full_url == SOURCE
        assert timeout == 15
        return _Body(json.dumps({**wire, "packet_bytes": 26}).encode(), SOURCE)

    with pytest.raises(CatalogError):
        sync_catalog(destination, now=1_700_000_100, opener=bad_opener)
    assert json.loads(written.read_text(encoding="utf-8"))["generated_at"] == 1_700_000_000
    secret = str(tmp_path / "credential-looking-directory")
    assert catalog_main(["sync", "--state", secret]) == 1
    leaked = capsys.readouterr()
    assert leaked.out == ""
    assert leaked.err == '{"error":"telemetry_release_catalog_sync_failed"}\n'
    assert secret not in leaked.err
    assert not Path(secret).exists()
