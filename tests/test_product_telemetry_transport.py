from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, closing, suppress
from datetime import datetime, timedelta, timezone
import json
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

from mnemion.product_telemetry import aggregate, delivery, endpoint, policy, transport


def _certificates(tmp_path_factory, common_name):
    folder = tmp_path_factory.mktemp("telemetry-tls")
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
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
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.num_tickets = 0
    context.load_cert_chain(certificate, private_key)
    context.telemetry_test_authorities = (certificate.read_text(),)
    return certificate, context


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    return _certificates(tmp_path_factory, "localhost")


@pytest.fixture
def installation(tmp_path, monkeypatch, certificates):
    assert policy.COLLECTION_AVAILABLE is False
    root = tmp_path / "private"
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "company.json")
    monkeypatch.setattr(
        endpoint,
        "release_certificate_authorities",
        lambda: certificates[1].telemetry_test_authorities,
    )
    budget = delivery.DeliveryBudget(root)

    def prepare(endpoint, *, reserve=True):
        authority = endpoint.host if endpoint.port == 443 else f"{endpoint.host}:{endpoint.port}"
        monkeypatch.setattr(policy, "COLLECTOR_URL", f"https://{authority}/v3/report")
        state = policy.configure(
            root,
            {
                "enabled": True,
                "expected_revision": 0,
                "disclosure_version": policy.DISCLOSURE_VERSION,
            },
        )
        if not reserve:
            return state
        assert aggregate.record(
            root,
            {"kind": "submission", "workflow": "memory.recall", "surface": "native_agent"},
            expected_revision=state["revision"],
            expected_generation=state["store_generation"],
        )
        report = budget.reserve(
            expected_revision=state["revision"],
            expected_generation=state["store_generation"],
            network="unmetered",
            constrained=False,
        )
        assert report is not None
        return report

    def cleaned(report):
        assert report._closed and report._body == b"\0" * 25
        with closing(sqlite3.connect(root / policy.DATABASE_NAME)) as database:
            assert database.execute("SELECT lease_token FROM delivery_state").fetchall() == [
                (None,)
            ]
            assert database.execute("SELECT count(*) FROM delivery_attempts").fetchone() == (1,)

    return SimpleNamespace(
        root=root, budget=budget, prepare=prepare, cleaned=cleaned, context=certificates[1]
    )


@pytest.fixture(scope="module")
def other_authority(tmp_path_factory):
    # A distinct issuer/key avoids a synthetic same-subject/no-key-identifier
    # collision. Ambient trust in the peer must not authorize this other root.
    return _certificates(tmp_path_factory, "other-test-authority")[0].read_text()


def test_scoped_tls_context_loads_one_authority_and_preserves_verification(
    installation, monkeypatch
):
    f = installation
    create = ssl.create_default_context
    contexts = []

    def observe(*args, **kwargs):
        context = create(*args, **kwargs)
        contexts.append(context.cert_store_stats())
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        return context

    monkeypatch.setattr(ssl, "create_default_context", observe)

    async def scenario():
        async with peer(f.context) as server:
            report = f.prepare(server.endpoint)
            result = await transport.send(f.budget, report, server.endpoint)
            assert result.outcome == "delivered" and len(server.requests) == 1
            f.cleaned(report)

    asyncio.run(scenario())
    assert contexts == [{"x509": 1, "crl": 0, "x509_ca": 1}]


def test_scoped_tls_rejects_a_peer_trusted_only_by_ambient_certificates(
    installation, monkeypatch, certificates, other_authority, tmp_path
):
    f = installation
    monkeypatch.setenv("SSL_CERT_FILE", str(certificates[0]))
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path / "absent-certificates"))

    async def scenario():
        async with peer(f.context) as server:
            target = transport.Endpoint(
                "localhost", "127.0.0.1", server.endpoint.port, (other_authority,)
            )
            report = f.prepare(target)
            result = await transport.send(f.budget, report, target)
            assert result.outcome == "failed" and server.requests == []
            f.cleaned(report)

    asyncio.run(scenario())


def test_scoped_tls_accepts_the_second_reviewed_rotation_authority(installation, other_authority):
    f = installation

    async def scenario():
        async with peer(f.context) as server:
            target = transport.Endpoint(
                "localhost",
                "127.0.0.1",
                server.endpoint.port,
                (other_authority, *server.endpoint.certificate_authorities),
            )
            report = f.prepare(target)
            result = await transport.send(f.budget, report, target)
            assert result.outcome == "delivered" and len(server.requests) == 1
            f.cleaned(report)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "authorities",
    [
        (),
        ("not-a-certificate",),
        ("-----BEGIN CERTIFICATE-----\nMAMCAQE=\n-----END CERTIFICATE-----\n",),
    ],
)
def test_absent_or_malformed_trust_never_connects(installation, monkeypatch, authorities):
    f = installation

    async def scenario():
        target = transport.Endpoint("localhost", "127.0.0.1", 443, authorities)
        report = f.prepare(target)
        connections = []

        async def forbidden_connect(*args):
            connections.append(True)
            raise AssertionError("unqualified trust connected")

        monkeypatch.setattr(asyncio.get_running_loop(), "sock_connect", forbidden_connect)
        result = await transport.send(f.budget, report, target)
        assert result.outcome in {"suppressed", "failed"} and connections == []
        f.cleaned(report)

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["set_error", "read_error", "oversized", "zero"])
def test_receive_buffer_refusal_never_connects_and_releases_the_reservation(
    installation, monkeypatch, failure
):
    f = installation
    sockets, connections = [], []
    real_socket = socket.socket

    class RefusingSocket(real_socket):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            sockets.append(self)

        def setsockopt(self, level, option, value):
            if (level, option) == (socket.SOL_SOCKET, socket.SO_RCVBUF):
                if failure == "set_error":
                    raise OSError("synthetic unavailable socket control")
            return super().setsockopt(level, option, value)

        def getsockopt(self, level, option, *args):
            if (level, option) == (socket.SOL_SOCKET, socket.SO_RCVBUF):
                if failure == "read_error":
                    raise OSError("synthetic unavailable socket observation")
                return 65536 if failure == "oversized" else 0
            return super().getsockopt(level, option, *args)

    async def scenario():
        async def forbidden_connect(*args):
            connections.append(True)
            raise AssertionError("An unbounded receive buffer must not connect")

        monkeypatch.setattr(socket, "socket", RefusingSocket)
        monkeypatch.setattr(asyncio.get_running_loop(), "sock_connect", forbidden_connect)
        target = transport.Endpoint(
            "localhost", "127.0.0.1", 443, f.context.telemetry_test_authorities
        )
        report = f.prepare(target)
        result = await transport.send(f.budget, report, target)
        assert result.outcome in {"failed", "suppressed"}
        assert result.encrypted_bytes_charged == 0 and connections == []
        assert len(sockets) == 1 and sockets[0].fileno() == -1
        f.cleaned(report)

    asyncio.run(scenario())


@pytest.mark.parametrize("ending", ["success", "shutdown", "pressure"])
def test_existing_loop_accepts_threaded_workflow_and_owns_tls_cleanup(installation, ending):
    from mnemion.product_telemetry import activity, workflow

    f = installation

    async def scenario():
        async with peer(f.context, "success" if ending == "success" else "hold") as server:
            f.prepare(server.endpoint, reserve=False)
            conditions = {"network": "unmetered", "constrained": False}
            owner = activity.Activity(f.root, server.endpoint, lambda: conditions)
            with activity._registry_lock:
                assert owner.root not in activity._owners
                activity._owners[owner.root] = owner
            try:

                def work():
                    operation = workflow.begin("memory.recall", "native_agent", root=f.root)
                    assert operation is not None
                    operation.finish("success", result_items=3)

                await asyncio.to_thread(work)
                await asyncio.wait_for(server.entered.wait(), 3)
                if ending == "shutdown":
                    await owner.close()
                else:
                    if ending == "pressure":
                        conditions["constrained"] = True
                    task = owner._task
                    if task is not None:
                        await asyncio.wait_for(task, 3)
                assert len(server.requests) == 1
                assert len(server.requests[0][1]) == 25
                with closing(sqlite3.connect(f.root / policy.DATABASE_NAME)) as db:
                    assert db.execute("SELECT lease_token FROM delivery_state").fetchone() == (
                        None,
                    )
                    assert db.execute("SELECT count(*) FROM delivery_attempts").fetchone() == (1,)
                # New work after completion cannot create an extra immediate
                # attempt or flush on shutdown, even when called by a thread.
                await asyncio.to_thread(work)
                await owner.close()
                assert len(server.requests) == 1
            finally:
                with activity._registry_lock:
                    del activity._owners[owner.root]
                await owner.close()

    asyncio.run(scenario())


def test_unavailable_application_owner_does_not_change_lifespan_errors(tmp_path):
    from mnemion.product_telemetry.activity import application_delivery

    async def scenario():
        with pytest.raises(ValueError, match="application failure"):
            async with application_delivery(root=tmp_path / "absent") as owner:
                assert owner is None
                raise ValueError("application failure")

    asyncio.run(scenario())
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("path", ["late_finish", "early_begin"])
@pytest.mark.parametrize("ending", ["ready", "opted_out", "closed"])
def test_queued_service_delivery_survives_collection_exhaustion(
    installation, monkeypatch, path, ending
):
    from mnemion.product_telemetry import activity, workflow

    f = installation
    now = [0.0]
    # Advance only the producer/owner clocks. Real TLS and asyncio deadlines
    # keep their real monotonic clock; this is not a resource measurement.
    monkeypatch.setattr(activity, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(workflow, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(
        aggregate, "time", SimpleNamespace(monotonic=lambda: now[0], time=time.time)
    )

    async def scenario():
        async with peer(f.context) as server:
            f.prepare(server.endpoint, reserve=False)
            ready, preparations = False, []

            async def prepare():
                preparations.append(None)
                return ready

            owner = activity.Activity(
                f.root,
                server.endpoint,
                lambda: {"network": "unmetered", "constrained": False},
                prepare=prepare,
            )

            async def settle():
                await asyncio.sleep(0)
                if owner._task is not None:
                    await asyncio.wait_for(owner._task, 3)

            with activity._registry_lock:
                assert owner.root not in activity._owners
                activity._owners[owner.root] = owner
            try:
                delayed = workflow.begin("memory.recall", "headless", root=f.root)
                assert delayed is not None
                for index in range(32):
                    now[0] = index * 0.5
                    active = workflow.begin("memory.recall", "headless", root=f.root)
                    assert active is not None
                    active.finish("success")
                    await settle()
                assert len(preparations) == 1 and server.requests == []
                ready = True
                if ending == "opted_out":
                    policy.configure(f.root, {"enabled": False, "expected_revision": 0})
                if ending == "closed":
                    await owner.close()
                now[0] = 60.001
                if path == "late_finish":
                    delayed.finish("success")
                else:
                    assert workflow.begin("memory.recall", "headless", root=f.root) is None
                await settle()
                expected = int(ending == "ready")
                assert len(server.requests) == expected
                assert len(preparations) == 1 + expected
                with closing(sqlite3.connect(f.root / policy.DATABASE_NAME)) as db:
                    assert db.execute("SELECT count(*) FROM delivery_attempts").fetchone() == (
                        expected,
                    )
                    assert db.execute("SELECT lease_token FROM delivery_state").fetchone() == (
                        None,
                    )
                delayed.finish("success")
                later = workflow.begin("memory.recall", "headless", root=f.root)
                if later is not None:
                    later.finish("success")
                await settle()
                assert len(server.requests) == expected
            finally:
                with activity._registry_lock:
                    del activity._owners[owner.root]
                await owner.close()

    asyncio.run(scenario())


def test_standalone_collection_does_not_import_a_delivery_lifetime(tmp_path):
    program = """
import json,sys
from pathlib import Path
from mnemion.product_telemetry import aggregate,policy,workflow
root=Path(sys.argv[1])/'private'
policy.COLLECTION_AVAILABLE=True
policy.COLLECTOR_URL='https://telemetry-fixture.invalid/v3/report'
policy.company_policy_file=lambda:root.parent/'company.json'
policy.configure(root,{'enabled':True,'expected_revision':0,'disclosure_version':policy.DISCLOSURE_VERSION})
before='mnemion.product_telemetry.activity' in sys.modules
active=workflow.begin('memory.recall','headless',root=root)
assert active is not None
active.finish('success')
print(json.dumps({'before':before,'after':'mnemion.product_telemetry.activity' in sys.modules,
                  'recorded':bool(aggregate.preview(root))}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", program, str(tmp_path)],
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    assert json.loads(completed.stdout) == {"before": False, "after": False, "recorded": True}


@pytest.mark.parametrize("ending", ["success", "wait_deadline", "opt_out", "approved_review"])
def test_managed_update_wait_sends_prior_queue_and_closes_before_returning(
    installation, monkeypatch, ending
):
    from mnemion.product_telemetry import activity, conditions, endpoint, inspection, workflow
    from mnemion.service import update_measurement as measured

    f = installation
    monkeypatch.setattr(policy, "default_directory", lambda: f.root)
    monkeypatch.setattr(endpoint, "release_address", lambda: "127.0.0.1")
    prepared, closed, reports = [], [], []

    class ReadyConditions:
        def __init__(self, **kwargs):
            pass

        async def prepare(self):
            prepared.append(True)
            return True

        def read(self):
            return {"network": "unmetered", "constrained": False}

        def close(self):
            closed.append(True)

    monkeypatch.setattr(conditions, "ServiceConditions", ReadyConditions)
    reserve = delivery.DeliveryBudget.reserve

    def observed_reserve(self, **kwargs):
        report = reserve(self, **kwargs)
        if report is not None:
            reports.append(report)
        return report

    monkeypatch.setattr(delivery.DeliveryBudget, "reserve", observed_reserve)

    async def scenario():
        mode = "hold" if ending in {"wait_deadline", "opt_out"} else "success"
        async with peer(f.context, mode) as server:
            f.prepare(server.endpoint, reserve=False)
            if ending == "approved_review":
                monkeypatch.setattr(
                    inspection,
                    "read_review_clock",
                    lambda **kwargs: {"epoch": "a" * 32, "elapsed_ms": 123456},
                )

                def action(name, **extra):
                    current = inspection.status(f.root)
                    return inspection.execute(
                        f.root,
                        name,
                        {
                            "expected_revision": current["status"]["revision"],
                            "expected_generation": current["status"]["store_generation"],
                            "expected_review_token": current["review"]["token"],
                            **extra,
                        },
                    )

                action("review_mode", mode="review")
            # Already-recorded observations survive only in the bounded product
            # queue. The new owner is not given an operational update journal.
            prior = workflow.begin("update.apply", "headless")
            assert prior is not None
            prior.finish("success")
            if ending == "approved_review":
                assert action("inspect_report")["review"]["outcome"] == "held"
                assert action("approve_report")["review"]["outcome"] == "approved"
                assert policy.status()["pending_records"] == 0

            def existing_watch_wait():
                with measured.automatic_watcher():
                    measured.quiet_wait(0.75, clock=time)
                    assert f.root.absolute() not in activity._owners
                    assert all(report._closed for report in reports)
                    # An ordinary next sleep is not an extra transmission or a
                    # fresh queue/policy inspection within the admission limit.
                    measured.quiet_wait(0.01, clock=time)

            waiting = asyncio.create_task(asyncio.to_thread(existing_watch_wait))
            await asyncio.wait_for(server.entered.wait(), 3)
            if ending == "opt_out":
                policy.configure(f.root, {"enabled": False, "expected_revision": 0})
            await asyncio.wait_for(waiting, 3)
            assert len(server.requests) == 1 and len(server.requests[0][1]) == 25
            assert len(prepared) == len(closed) == len(reports) == 1
            assert reports[0]._body == b"\0" * 25
            with closing(sqlite3.connect(f.root / policy.DATABASE_NAME)) as database:
                assert database.execute("SELECT lease_token FROM delivery_state").fetchone() == (
                    None,
                )
                assert database.execute("SELECT count(*) FROM delivery_attempts").fetchone() == (1,)

    asyncio.run(scenario())


@pytest.mark.parametrize("ending", ["success", "opt_out", "shutdown"])
def test_service_preparation_rechecks_policy_and_closes_without_idle_os_queries(
    installation, ending
):
    from mnemion.product_telemetry.activity import Activity

    f = installation

    async def scenario():
        async with peer(f.context) as server:
            state = f.prepare(server.endpoint, reserve=False)
            preparations, closes = [], []
            entered, release = asyncio.Event(), asyncio.Event()

            async def prepare():
                preparations.append(None)
                entered.set()
                await release.wait()
                return True

            owner = Activity(
                f.root,
                server.endpoint,
                lambda: {"network": "unmetered", "constrained": False},
                prepare=prepare,
                cleanup=lambda: closes.append(None),
            )
            stamp = {
                "expected_revision": state["revision"],
                "expected_generation": state["store_generation"],
            }
            assert owner.budget.eligible(**stamp) is False
            assert aggregate.record(
                f.root,
                {"kind": "submission", "workflow": "memory.recall", "surface": "native_agent"},
                **stamp,
            )
            assert owner.budget.eligible(**stamp) is True
            owner.offer(state["revision"], state["store_generation"])
            try:
                await asyncio.wait_for(entered.wait(), 1)
                if ending == "opt_out":
                    policy.configure(f.root, {"enabled": False, "expected_revision": 0})
                if ending == "shutdown":
                    await owner.close()
                else:
                    release.set()
                    await asyncio.wait_for(owner._task, 2)
                assert len(preparations) == len(closes) == 1
                attempts = 1 if ending == "success" else 0
                assert len(server.requests) == attempts
                with closing(sqlite3.connect(f.root / policy.DATABASE_NAME)) as db:
                    assert db.execute("SELECT count(*) FROM delivery_attempts").fetchone() == (
                        attempts,
                    )
                    assert db.execute("SELECT lease_token FROM delivery_state").fetchone() == (
                        None,
                    )
                if ending == "success":
                    assert aggregate.record(
                        f.root,
                        {
                            "kind": "submission",
                            "workflow": "memory.save",
                            "surface": "native_agent",
                        },
                        **stamp,
                    )
                    owner._next_check = 0
                    owner.offer(state["revision"], state["store_generation"])
                    await asyncio.sleep(0)
                    await asyncio.wait_for(owner._task, 1)
                    assert len(preparations) == 1
                    assert len(server.requests) == 1
                else:
                    assert owner.budget.eligible(**stamp) is False or ending == "shutdown"
            finally:
                release.set()
                await owner.close()

    asyncio.run(scenario())


@asynccontextmanager
async def peer(context, mode="success"):
    entered, release = asyncio.Event(), asyncio.Event()
    requests, tasks = [], set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            if mode == "stall_handshake":
                await reader.read(4096)
                entered.set()
                await release.wait()
                return
            headers = await reader.readuntil(b"\r\n\r\n")
            declared = headers.partition(b"Content-Length: ")[2].partition(b"\r\n")[0]
            body = await reader.readexactly(int(declared))
            requests.append((headers, body))
            entered.set()
            if mode == "hold":
                await release.wait()
            response = b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            if mode == "redirect":
                response = b"HTTP/1.1 302 Found\r\nLocation: https://example.invalid/private\r\nContent-Length: 0\r\n\r\n"
            if mode == "large_headers":
                response = b"HTTP/1.1 204 No Content\r\nX-Noise: " + b"a" * 4096 + b"\r\n\r\n"
            writer.write(response)
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(
        handle, "127.0.0.1", 0, ssl=None if mode == "stall_handshake" else context
    )
    endpoint = transport.Endpoint(
        "localhost",
        "127.0.0.1",
        server.sockets[0].getsockname()[1],
        context.telemetry_test_authorities,
    )
    try:
        yield SimpleNamespace(
            endpoint=endpoint, entered=entered, release=release, requests=requests
        )
    finally:
        release.set()
        server.close()
        await server.wait_closed()
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*list(tasks), return_exceptions=True)


def test_tls_handoff_is_one_25_byte_request_without_dns_credentials_or_retries(
    installation, monkeypatch
):
    f = installation

    async def run():
        async with peer(f.context) as server:
            report = f.prepare(server.endpoint)
            original = bytes(report._body)

            def forbidden_dns(*_args, **_kwargs):
                raise AssertionError("No system resolver may be started")

            monkeypatch.setattr(socket, "getaddrinfo", forbidden_dns)
            result = await transport.send(f.budget, report, server.endpoint)
            assert result.outcome == "delivered"
            assert 0 < result.encrypted_bytes_charged <= transport.MAX_TLS_BYTES
            assert len(server.requests) == 1 and server.requests[0][1] == original
            headers = server.requests[0][0]
            assert headers.startswith(b"POST /v3/report HTTP/1.1\r\n")
            assert b"Content-Length: 25\r\n" in headers
            names = {line.split(b":", 1)[0].lower() for line in headers.split(b"\r\n")[1:] if line}
            assert names == {b"host", b"content-type", b"content-length", b"connection"}
            f.cleaned(report)
            assert (await transport.send(f.budget, report, server.endpoint)).outcome == "suppressed"
            assert len(server.requests) == 1

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["hold", "stall_handshake"])
def test_opt_out_closes_pending_tls_io_promptly_and_keeps_spending(installation, mode):
    f = installation

    async def run():
        async with peer(f.context, mode) as server:
            report = f.prepare(server.endpoint)
            task = asyncio.create_task(transport.send(f.budget, report, server.endpoint))
            await asyncio.wait_for(server.entered.wait(), 2)
            policy.configure(f.root, {"enabled": False, "expected_revision": 0})
            result = await asyncio.wait_for(task, 1)
            assert result.outcome == "suppressed"
            assert len(server.requests) == (1 if mode == "hold" else 0)
            f.cleaned(report)

    asyncio.run(run())


def test_caller_cancellation_is_propagated_and_cleans_the_active_socket_and_lease(installation):
    f = installation

    async def run():
        async with peer(f.context, "hold") as server:
            report = f.prepare(server.endpoint)
            task = asyncio.create_task(transport.send(f.budget, report, server.endpoint))
            await asyncio.wait_for(server.entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 1)
            f.cleaned(report)

    asyncio.run(run())


def test_concurrent_senders_share_one_connection_and_leave_the_winner_intact(installation):
    f = installation

    async def run():
        async with peer(f.context) as server:
            report = f.prepare(server.endpoint)
            results = await asyncio.gather(
                *[transport.send(f.budget, report, server.endpoint) for _ in range(2)]
            )
            assert sorted(result.outcome for result in results) == ["delivered", "suppressed"]
            assert (
                sum(result.encrypted_bytes_charged for result in results) <= transport.MAX_TLS_BYTES
            )
            assert len(server.requests) == 1
            f.cleaned(report)

    asyncio.run(run())


def test_a_second_sender_cannot_cancel_a_request_already_waiting_for_its_response(installation):
    f = installation

    async def run():
        async with peer(f.context, "hold") as server:
            report = f.prepare(server.endpoint)
            first = asyncio.create_task(transport.send(f.budget, report, server.endpoint))
            await asyncio.wait_for(server.entered.wait(), 2)
            second = await transport.send(f.budget, report, server.endpoint)
            assert second == transport.AttemptResult("suppressed")
            assert f.budget.current(report)
            server.release.set()
            assert (await asyncio.wait_for(first, 1)).outcome == "delivered"
            assert len(server.requests) == 1
            f.cleaned(report)

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["redirect", "large_headers"])
def test_response_limits_and_redirects_never_create_another_request(installation, mode):
    f = installation

    async def run():
        async with peer(f.context, mode) as server:
            report = f.prepare(server.endpoint)
            result = await transport.send(f.budget, report, server.endpoint)
            assert result.outcome == "failed" and len(server.requests) == 1
            assert result.encrypted_bytes_charged <= transport.MAX_TLS_BYTES
            f.cleaned(report)

    asyncio.run(run())


def test_wrong_certificate_name_prevents_the_report_body_from_being_sent(installation):
    f = installation

    async def run():
        async with peer(f.context) as server:
            endpoint = transport.Endpoint(
                "wrong.invalid",
                "127.0.0.1",
                server.endpoint.port,
                server.endpoint.certificate_authorities,
            )
            report = f.prepare(endpoint)
            result = await transport.send(f.budget, report, endpoint)
            assert result.outcome == "failed" and not server.requests
            f.cleaned(report)

    asyncio.run(run())


def test_tls_byte_limit_stops_an_incomplete_handshake_without_application_data(
    installation, monkeypatch
):
    f = installation
    monkeypatch.setattr(transport, "MAX_TLS_BYTES", 512)

    async def run():
        async with peer(f.context) as server:
            report = f.prepare(server.endpoint)
            result = await transport.send(f.budget, report, server.endpoint)
            assert result.outcome == "wire_limit"
            assert result.encrypted_bytes_charged <= 512 and not server.requests
            f.cleaned(report)

    asyncio.run(run())


def test_real_five_second_deadline_stops_a_silent_peer(installation):
    f = installation

    async def run():
        async with peer(f.context, "stall_handshake") as server:
            report = f.prepare(server.endpoint)
            started = asyncio.get_running_loop().time()
            result = await asyncio.wait_for(transport.send(f.budget, report, server.endpoint), 6)
            elapsed = asyncio.get_running_loop().time() - started
            assert result.outcome in {"deadline", "suppressed"}
            assert 4.5 < elapsed < 5.5 and not server.requests
            f.cleaned(report)

    asyncio.run(run())
