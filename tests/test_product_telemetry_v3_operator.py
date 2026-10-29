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
import socket
import ssl
import subprocess
import sys
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

from mnemion.product_telemetry.aggregate_v3 import NUMERATOR, AggregateWindow
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
            {"type": "http", "method": "POST", "path": "/v1/report", "query_string": b"", "headers": []},
            None,
            None,
        )
    )
    assert seen["path"] == "/"
    with pytest.raises(ConfigurationError):
        MetadataBoundary(app, route="/v3/report?week=1")


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
    clock = lambda: stamp(current)
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
    assert csv_text.splitlines()[0].startswith("record,ordinary_privacy_settings_contain_fleet_data")
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
    assert any(metric["quantiles"]["p50"]["state"] == "bucket_bounds" for metric in release["metrics"] if "quantiles" in metric)
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
        for metric in next(item for item in again["weeks"] if item["week"] == current - 1)["release"]
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
    assert exported_view["publication_failures"] == [{"window_week": current - 3, "state": "publication_failed"}]
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
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
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
            ready = b"OPTIONS /v3/report HTTP/1.1\r\nHost: localhost\r\n\r\n" if mode == "v3" else (
                b"OPTIONS /v1/report HTTP/1.1\r\nHost: localhost\r\n\r\n"
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
    malformed = b"POST /v3/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: 25\r\n\r\n" + (b"\x00" * 25)
    wrong = (
        b"POST /v1/report HTTP/1.1\r\nHost: localhost\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    queried = b"POST /v3/report?" + CANARY + b" HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n"
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
