"""OS admission, freshness and cancellation; no real network settings changed."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import ctypes
import json
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
from threading import Event, Thread

import pytest

from mnemion.product_telemetry.network import NativeNetworkConditions, network_flags


class CpuTotals(ctypes.Structure):
    _fields_ = [("idle", ctypes.c_uint64), ("total", ctypes.c_uint64), ("count", ctypes.c_uint32)]


@pytest.mark.parametrize(
    "value", [True, False, None, "9", float("nan"), 1, 2, 3, 7, 11, 15, 256, -1]
)
def test_invalid_os_values_never_grant_an_unmetered_path(value):
    assert network_flags(value) == {"network": "unknown", "constrained": True, "observed": False}


def test_fixed_flags_have_no_identifiers_or_automatic_unknown_override():
    assert network_flags(0) == {"network": "unknown", "constrained": False, "observed": False}
    assert network_flags(9) == {"network": "unmetered", "constrained": False, "observed": True}
    assert network_flags(14) == {"network": "metered", "constrained": True, "observed": True}


def test_an_additional_detector_cannot_erase_the_os_metered_veto():
    from mnemion.product_telemetry.conditions import ServiceConditions

    async def run():
        network = NativeNetworkConditions(probe=lambda: 10)
        conditions = ServiceConditions(metering=lambda: "unmetered", network=network)
        try:
            assert await network.start()
            assert conditions.read()["network"] == "metered"
        finally:
            conditions.close()

    asyncio.run(run())


def test_os_queries_have_no_idle_or_closed_refresh_and_preserve_metered_restrictions():
    async def run():
        calls, now, code = [], [0.0], [9]

        def probe():
            calls.append(None)
            return code[0]

        gauge = NativeNetworkConditions(probe=probe, now=lambda: now[0])
        assert gauge.read() == {"network": "unknown", "constrained": True}
        await asyncio.sleep(0)
        assert not calls
        assert await gauge.start()
        assert gauge.read() == {"network": "unmetered", "constrained": False}
        now[0], code[0] = 0.3, 10
        gauge.read()
        gauge.read()
        await asyncio.shield(gauge._pending)
        assert len(calls) == 2
        assert gauge.read() == {"network": "metered", "constrained": False}
        gauge.close()
        code[0] = 0
        assert await gauge.start()
        assert gauge.read() == {"network": "metered", "constrained": False}
        gauge.close()
        code[0] = 9
        assert await gauge.start()
        assert gauge.read() == {"network": "unmetered", "constrained": False}
        gauge.close()
        now[0] = 100
        gauge.read()
        await asyncio.sleep(0)
        assert len(calls) == 4

    asyncio.run(run())


def test_cancelled_os_call_is_not_adopted_or_overlapped():
    async def run():
        calls, finish = [], Event()
        entered = asyncio.Event()
        loop = asyncio.get_running_loop()

        def probe():
            calls.append(None)
            if len(calls) == 1:
                loop.call_soon_threadsafe(entered.set)
                assert finish.wait(2)
                return 9
            return 10

        gauge = NativeNetworkConditions(probe=probe)
        first = asyncio.create_task(gauge.start())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            second = asyncio.create_task(gauge.start())
            await asyncio.sleep(0)
            assert len(calls) == 1
            assert gauge.read()["constrained"] is True
            finish.set()
            assert await second
            assert len(calls) == 2
            assert gauge.read() == {"network": "metered", "constrained": False}
        finally:
            finish.set()
            gauge.close()

    asyncio.run(run())


def test_stale_pending_sample_and_clock_rollback_suppress_handoff():
    async def run():
        now, calls, finish = [0.0], [], Event()

        def probe():
            calls.append(None)
            if len(calls) > 1:
                assert finish.wait(2)
            return 9

        gauge = NativeNetworkConditions(probe=probe, now=lambda: now[0])
        try:
            assert await gauge.start()
            now[0] = 1.1
            assert gauge.read() == {"network": "unknown", "constrained": True}
            pending = gauge._pending
            gauge.read()
            assert gauge._pending is pending
            finish.set()
            await asyncio.shield(pending)
            assert gauge.read() == {"network": "unmetered", "constrained": False}
            now[0] = 1.0
            assert gauge.read()["constrained"] is True
        finally:
            finish.set()
            gauge.close()

    asyncio.run(run())


def test_one_second_deadline_closes_preparation_without_detaching_the_native_call():
    async def run():
        finish = Event()

        def probe():
            assert finish.wait(2)
            return 9

        gauge = NativeNetworkConditions(probe=probe)
        try:
            assert await gauge.start() is False
            assert gauge.read()["constrained"] is True
            pending = gauge._pending
            assert pending is not None and not pending.cancelled()
            finish.set()
            await asyncio.shield(pending)
            assert gauge.read()["constrained"] is True
        finally:
            finish.set()
            gauge.close()

    asyncio.run(run())


def test_cancel_before_a_busy_executor_starts_does_not_query_the_os():
    async def run():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        finish, calls = Event(), []
        busy = loop.run_in_executor(None, lambda: finish.wait(2))
        gauge = NativeNetworkConditions(probe=lambda: calls.append(None) or 9)
        started = asyncio.create_task(gauge.start())
        try:
            await asyncio.sleep(0)
            pending = gauge._pending
            assert pending is not None
            started.cancel()
            with pytest.raises(asyncio.CancelledError):
                await started
            finish.set()
            await asyncio.shield(busy)
            await asyncio.shield(pending)
            assert not calls
        finally:
            finish.set()
            gauge.close()

    asyncio.run(run())


def test_slow_os_reply_does_not_extend_freshness_after_the_query_deadline():
    async def run():
        finish, entered, now = Event(), asyncio.Event(), [0.0]
        loop = asyncio.get_running_loop()

        def probe():
            loop.call_soon_threadsafe(entered.set)
            assert finish.wait(2)
            return 9

        gauge = NativeNetworkConditions(probe=probe, now=lambda: now[0])
        try:
            started = asyncio.create_task(gauge.start())
            await asyncio.wait_for(entered.wait(), 1)
            now[0] = 0.6
            finish.set()
            assert await started
            now[0] = 1.001
            assert gauge.read()["constrained"] is True
        finally:
            gauge.close()
            finish.set()

    asyncio.run(run())


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    if sys.platform != "linux" or not shutil.which("cc"):
        pytest.skip("This source decoder fixture needs the Linux system C compiler")
    source = (
        Path(__file__).resolve().parents[1] / "mnemion/product_telemetry/native/network-state.c"
    )
    output = tmp_path_factory.mktemp("network-core") / "network-state.node"
    # Retain decoder symbols only in this private fixture. Release builds hide
    # them and expose the versioned policy/aggregate C ABI plus Node registration.
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O2",
            "-fPIC",
            "-shared",
            str(source),
            "-pthread",
            "-ldl",
            "-o",
            str(output),
        ],
        check=True,
        timeout=30,
    )
    library = ctypes.CDLL(str(output))
    library.mnemion_network_state_v1.argtypes = []
    library.mnemion_network_state_v1.restype = ctypes.c_uint32
    library.mnm_windows_cost.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    library.mnm_windows_cost.restype = ctypes.c_uint32
    library.mnm_linux_cost.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    library.mnm_linux_cost.restype = ctypes.c_uint32
    library.mnemion_cpu_totals_v1.argtypes = [ctypes.POINTER(CpuTotals)]
    library.mnemion_cpu_totals_v1.restype = ctypes.c_int
    library.mnm_cpu_totals.argtypes = [ctypes.c_uint64] * 5 + [
        ctypes.c_uint32,
        ctypes.POINTER(CpuTotals),
    ]
    library.mnm_cpu_totals.restype = ctypes.c_int
    library.mnm_linux_cpu_totals.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.POINTER(CpuTotals),
    ]
    library.mnm_linux_cpu_totals.restype = ctypes.c_int
    return library, output


def test_linux_cpu_aggregate_preserves_node_busy_time_without_per_core_metadata(compiled):
    library, _ = compiled
    value = CpuTotals()
    line = b"cpu  100 20 30 400 99999 5 77777 888 9 0\n"
    assert library.mnm_linux_cpu_totals(line, len(line), 4, ctypes.byref(value)) == 1
    assert (value.idle, value.total, value.count) == (400, 555, 4)
    # iowait, softirq and guest columns must not silently change the admission
    # definition previously supplied by the Linux Node/libuv CPU times API.
    changed = b"cpu  100 20 30 400 0 5 0 0 0 0\n"
    assert library.mnm_linux_cpu_totals(changed, len(changed), 4, ctypes.byref(value)) == 1
    assert (value.idle, value.total, value.count) == (400, 555, 4)
    assert library.mnemion_cpu_totals_v1(ctypes.byref(value)) == 1
    assert 0 <= value.idle <= value.total <= 2**53 - 1
    assert value.total > 0 and 0 < value.count <= 1048576
    assert library.mnemion_cpu_totals_v1(None) == 0


@pytest.mark.parametrize(
    "line,count",
    [
        (None, 1),
        (b"", 1),
        (b"cpu0 1 2 3 4 5 6\n", 1),
        (b"cpu 1 2 3 4 5\n", 1),
        (b"cpu 1 2 3 4 5 6", 1),
        (b"cpu 1 2 3 4 5 6x\n", 1),
        (b"cpu 1 2 3 4 -5 6\n", 1),
        (b"cpu 1 2 3 4 5 18446744073709551616\n", 1),
        (b"cpu 0 0 0 9007199254740991 0 1\n", 1),
        (b"cpu 0 0 0 0 0 0\n", 1),
        (b"cpu 1 2 3 4 5 6\n", 0),
        (b"cpu 1 2 3 4 5 6\n", 1048577),
        (b"cpu " + b" " * 500 + b"1 2 3 4 5 6\n", 1),
    ],
)
def test_cpu_parser_rejects_truncation_overflow_and_unknown_samples(compiled, line, count):
    library, _ = compiled
    value = CpuTotals(123, 456, 2)
    length = len(line) if line is not None else 20
    assert library.mnm_linux_cpu_totals(line, length, count, ctypes.byref(value)) == 0
    assert (value.idle, value.total, value.count) == (0, 0, 0)


def test_native_cpu_totals_never_wrap_or_round_a_js_counter(compiled):
    library, _ = compiled
    value = CpuTotals()
    maximum = 2**53 - 1
    assert library.mnm_cpu_totals(maximum - 1, 1, 0, 0, 0, 1, ctypes.byref(value)) == 1
    assert (value.idle, value.total, value.count) == (maximum - 1, maximum, 1)
    for idle, user in [(maximum, 1), (2**64 - 1, 1), (0, 0)]:
        assert library.mnm_cpu_totals(idle, user, 0, 0, 0, 1, ctypes.byref(value)) == 0
        assert (value.idle, value.total, value.count) == (0, 0, 0)


@pytest.mark.parametrize(
    "cost,expected", [(0, 8), (1, 9), (2, 10), (3, 10), (4, 12), (0xFFFFFFFF, 12)]
)
def test_windows_hint_cost_never_mistakes_fixed_variable_or_future_values_for_unmetered(
    compiled, cost, expected
):
    library, _ = compiled
    assert library.mnm_windows_cost(cost, 3, 0, 0, 0) == expected
    for flags in [(1, 0, 0), (0, 1, 0), (0, 0, 1)]:
        assert library.mnm_windows_cost(cost, 3, *flags) & 2
    for level in [0, 1, 2, 4, 5, 6, 0xFFFFFFFF]:
        assert library.mnm_windows_cost(cost, level, 0, 0, 0) & 4


@pytest.mark.parametrize(
    "cost,expected", [(0, 8), (1, 10), (2, 9), (3, 10), (4, 8), (5, 12), (0xFFFFFFFF, 12)]
)
def test_linux_guessed_no_is_unknown_and_only_global_connectivity_can_allow_delivery(
    compiled, cost, expected
):
    library, _ = compiled
    assert library.mnm_linux_cost(cost, 70) == expected
    for state in [0, 10, 20, 30, 40, 50, 60, 80, 0xFFFFFFFF]:
        assert library.mnm_linux_cost(cost, state) & 4


def test_python_loads_the_real_native_abi_without_returning_other_os_data(compiled, monkeypatch):
    from mnemion.product_telemetry import network

    _, artifact = compiled
    monkeypatch.setattr(network, "__file__", str(artifact.with_name("network.py")))
    monkeypatch.setattr(network, "_native", None)
    assert network.native_state() in (0, 8, 9, 10, 12, 13, 14)


def test_missing_source_install_probe_stays_unknown(compiled, tmp_path, monkeypatch):
    from mnemion.product_telemetry import network

    monkeypatch.setattr(network, "__file__", str(tmp_path / "network.py"))
    monkeypatch.setattr(network, "_native", None)
    assert network.native_state() == 0


def compile_private_bus_probe(output, address):
    source = (
        Path(__file__).resolve().parents[1] / "mnemion/product_telemetry/native/network-state.c"
    )
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O2",
            "-fPIC",
            "-shared",
            str(source),
            f'-DMNEMION_NETWORK_TEST_BUS="{address}"',
            "-pthread",
            "-ldl",
            "-o",
            str(output),
        ],
        check=True,
        timeout=30,
    )


@pytest.fixture
def private_bus(tmp_path, compiled):
    system_python = Path("/usr/bin/python3")
    if not shutil.which("dbus-daemon") or not system_python.is_file():
        pytest.skip("Private bus acceptance needs system D-Bus")
    available = subprocess.run(
        [str(system_python), "-c", "import dbus; from gi.repository import GLib"],
        capture_output=True,
    )
    if available.returncode:
        pytest.skip("Private bus acceptance needs system python3-dbus and python3-gi")
    address = "unix:path=" + str(tmp_path / "private-bus.sock")
    daemon = subprocess.Popen(
        [
            "dbus-daemon",
            "--session",
            "--nofork",
            "--nopidfile",
            "--print-address=1",
            "--address=" + address,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    helper = None

    def line(process):
        assert select.select([process.stdout], [], [], 3)[0], "Private bus fixture did not answer"
        value = process.stdout.readline()
        assert value, "Private bus fixture exited"
        return value

    try:
        assert line(daemon).startswith(address)
        helper = subprocess.Popen(
            [
                str(system_python),
                str(Path(__file__).parent / "fixtures/telemetry_network_bus.py"),
                address,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert json.loads(line(helper)) == {"ready": True}
        output = tmp_path / "network-state.node"
        compile_private_bus_probe(output, address)
        library = ctypes.CDLL(str(output))
        library.mnemion_network_state_v1.restype = ctypes.c_uint32
        library.mnemion_network_state_v1.argtypes = []

        def command(value):
            helper.stdin.write(json.dumps(value) + "\n")
            helper.stdin.flush()
            return json.loads(line(helper))

        yield library.mnemion_network_state_v1, command
    finally:
        for process in (helper, daemon):
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()


def test_actual_linux_bus_reads_only_cost_and_state_without_daemon_activation(
    private_bus, monkeypatch
):
    probe, command = private_bus
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", "tcp:host=never-contact.invalid,port=1234")
    for cost, state, expected in [
        (2, 70, 9),
        (1, 70, 10),
        (3, 70, 10),
        (4, 70, 8),
        (0, 70, 8),
        (2, 60, 13),
        (5, 70, 12),
    ]:
        assert command({"cost": cost, "state": state, "format": "uint", "delay": 0}) == {"ok": True}
        assert probe() == expected
        assert command("stats")["calls"] == [
            {
                "method": "Get",
                "auto_start": False,
                "arguments": ["org.freedesktop.NetworkManager", property],
            }
            for property in ["Metered", "State"]
        ]


def test_actual_linux_bus_rejects_wrong_types_and_late_replies(private_bus):
    probe, command = private_bus
    for format in ["string", "signed"]:
        command({"format": format, "delay": 0})
        assert probe() == 0
        assert len(command("stats")["calls"]) == 1
    command({"format": "uint", "delay": 400})
    assert probe() == 0
    command({"format": "uint", "cost": 1, "delay": 0})
    assert probe() == 10


def test_stalled_linux_bus_authentication_cannot_keep_the_probe_alive(tmp_path, compiled):
    address = tmp_path / "stalled.sock"
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(address))
    listener.listen(1)
    listener.settimeout(3)
    finish = Event()

    def peer():
        try:
            connection, _ = listener.accept()
            with connection:
                finish.wait(3)
        except OSError:
            pass

    worker = Thread(target=peer, daemon=True)
    worker.start()
    output = tmp_path / "network-state.node"
    try:
        compile_private_bus_probe(output, "unix:path=" + str(address))
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "import ctypes,json,sys,time; f=ctypes.CDLL(sys.argv[1]).mnemion_network_state_v1; f.restype=ctypes.c_uint32; start=time.monotonic(); value=f(); print(json.dumps({'value':value,'seconds':time.monotonic()-start}))",
                str(output),
            ],
            text=True,
            capture_output=True,
            timeout=2,
            check=True,
        )
        result = json.loads(child.stdout)
        assert result["value"] == 0
        assert result["seconds"] < 1
    finally:
        finish.set()
        listener.close()
        worker.join(timeout=3)
