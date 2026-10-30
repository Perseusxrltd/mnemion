"""Immutable progress snapshots stay readable while the next one is published."""

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from deploy.report_telemetry_renderer import read_owned_marker

_MODULE = Path(__file__).resolve().parents[1] / "studio" / "electron" / "canonical-memory-cycles.mjs"
_TIMEOUT = 10


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.fail("node is required for the progress snapshot checks")
    return node


def _wait_line(stream, timeout: float) -> bytes | None:
    found: list[bytes] = []

    def read() -> None:
        found.append(stream.readline())

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive() or not found:
        return None
    return found[0]


def _fail_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=_TIMEOUT)
    error = process.stderr.read() if process.stderr is not None else b""
    raise AssertionError(error)


def test_missing_and_unreadable_markers_stay_absent(tmp_path: Path):
    assert read_owned_marker(tmp_path) is None
    root = tmp_path / "marker"
    root.mkdir()
    (root / "monitor.json").write_text("not-json", encoding="utf-8")
    assert read_owned_marker(root) is None
    (root / "monitor.json").write_bytes(b"{" + b"x" * 65536)
    assert read_owned_marker(root) is None
    (root / "monitor.json").write_text("[1]", encoding="utf-8")
    assert read_owned_marker(root) is None
    (root / "monitor.json").write_text('{"phase":"measuring","at_ms":1}', encoding="utf-8")
    assert read_owned_marker(root) == {"phase": "measuring", "at_ms": 1}
    (root / "owned-progress").mkdir()
    assert read_owned_marker(root) is None


def test_snapshot_reader_rejects_partial_gap_and_mtime(tmp_path: Path):
    progress = tmp_path / "owned-progress"
    progress.mkdir()
    (progress / "01.json").write_text('{"phase":"16_memory_cycles","at_ms":16}', encoding="utf-8")
    (progress / "02.json.tmp").write_text("{", encoding="utf-8")
    assert read_owned_marker(tmp_path) == {"phase": "16_memory_cycles", "at_ms": 16}
    (progress / "02.json").write_text("not-json", encoding="utf-8")
    (progress / "02.json.tmp").unlink()
    assert read_owned_marker(tmp_path) is None
    (progress / "02.json").write_text("[]", encoding="utf-8")
    assert read_owned_marker(tmp_path) is None
    (progress / "02.json").write_text('{"phase":"32_memory_cycles","at_ms":32}', encoding="utf-8")
    os.utime(progress / "01.json", (2_000_000_000, 2_000_000_000))
    os.utime(progress / "02.json", (1_000_000_000, 1_000_000_000))
    assert read_owned_marker(tmp_path)["phase"] == "32_memory_cycles"
    (progress / "03.json").write_text('{"phase":"64_memory_cycles","at_ms":64}', encoding="utf-8")
    (progress / "02.json").unlink()
    assert read_owned_marker(tmp_path) is None
    (progress / "03.json").unlink()
    (progress / "notes.txt").write_text("extra", encoding="utf-8")
    assert read_owned_marker(tmp_path) is None
    (progress / "notes.txt").unlink()
    (progress / "01.json").write_bytes(b"{" + b"x" * 1024)
    assert read_owned_marker(tmp_path) is None


def test_writer_capacity_exclusive_names_and_owned_temp(tmp_path: Path):
    script = tmp_path / "capacity.mjs"
    script.write_text(
        "import { mkdirSync, writeFileSync, writeSync } from 'node:fs'\n"
        f"import {{ canonicalMemoryCycles, canonicalProgressWriter }} from {json.dumps(_MODULE.as_uri())}\n"
        "if (canonicalMemoryCycles.toString().includes('canonicalProgressWriter')) throw new Error('closed')\n"
        "const root = process.argv[2]\n"
        "const reuse = canonicalProgressWriter(root + '/reuse')\n"
        "reuse({ phase: 'starting', at_ms: 1 })\n"
        "let reuseRejected = false\n"
        "try { canonicalProgressWriter(root + '/reuse') } catch (error) {\n"
        "  reuseRejected = error.message === 'Progress snapshot name already used'\n"
        "}\n"
        "if (!reuseRejected) throw new Error('reuse')\n"
        "const planted = canonicalProgressWriter(root + '/planted')\n"
        "writeFileSync(root + '/planted/01.json.tmp', 'partial')\n"
        "let plantedRejected = false\n"
        "try { planted({ phase: 'starting', at_ms: 1 }) } catch (error) {\n"
        "  plantedRejected = error.message === 'Progress snapshot name already used'\n"
        "}\n"
        "if (!plantedRejected) throw new Error('planted')\n"
        "const occupied = canonicalProgressWriter(root + '/occupied')\n"
        "writeFileSync(root + '/occupied/01.json', '{\"phase\":\"foreign\"}')\n"
        "let occupiedRejected = false\n"
        "try { occupied({ phase: 'starting', at_ms: 1 }) } catch (error) {\n"
        "  occupiedRejected = error.message === 'Progress snapshot name already used'\n"
        "}\n"
        "if (!occupiedRejected) throw new Error('occupied')\n"
        "const oversized = canonicalProgressWriter(root + '/oversized')\n"
        "let invalid = false\n"
        "try { oversized([]) } catch (error) { invalid = error.message === 'Progress record invalid' }\n"
        "if (!invalid) throw new Error('invalid')\n"
        "let tooBig = false\n"
        "try { oversized({ phase: 'x'.repeat(2000), at_ms: 1 }) } catch (error) {\n"
        "  tooBig = error.message === 'Progress record oversized'\n"
        "}\n"
        "if (!tooBig) throw new Error('oversized')\n"
        "mkdirSync(root + '/sample')\n"
        "const publish = canonicalProgressWriter(root + '/sample/owned-progress')\n"
        "for (let index = 1; index <= 64; index += 1) publish({ phase: 'measuring', at_ms: index })\n"
        "let capped = false\n"
        "try { publish({ phase: 'measuring', at_ms: 65 }) } catch (error) {\n"
        "  capped = error.message === 'Progress snapshot capacity exceeded'\n"
        "}\n"
        "if (!capped) throw new Error('capacity')\n"
        "writeSync(1, 'ok\\n')\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [_node(), str(script), str(tmp_path)],
        check=False,
        capture_output=True,
        timeout=_TIMEOUT,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == b"ok\n"
    progress = tmp_path / "sample" / "owned-progress"
    assert sorted(path.name for path in progress.iterdir()) == [
        f"{index:02d}.json" for index in range(1, 65)
    ]
    assert (tmp_path / "planted" / "01.json.tmp").read_text(encoding="utf-8") == "partial"
    assert not (tmp_path / "planted" / "01.json").exists()
    assert (tmp_path / "occupied" / "01.json").read_text(encoding="utf-8") == '{"phase":"foreign"}'
    assert list((tmp_path / "occupied").glob("*.tmp")) == []
    assert list((tmp_path / "oversized").iterdir()) == []
    assert read_owned_marker(tmp_path / "sample")["at_ms"] == 64


def test_publish_next_snapshot_while_prior_is_held(tmp_path: Path):
    script = tmp_path / "publish-progress.mjs"
    script.write_text(
        "import { writeSync } from 'node:fs'\n"
        f"import {{ canonicalProgressWriter }} from {json.dumps(_MODULE.as_uri())}\n"
        "const publish = canonicalProgressWriter(process.argv[2])\n"
        "publish({ phase: '16_memory_cycles', at_ms: 16 })\n"
        "writeSync(1, 'ready\\n')\n"
        "await new Promise(resolve => process.stdin.once('data', () => resolve()))\n"
        "process.stdin.pause()\n"
        "process.stdin.unref()\n"
        "publish({ phase: '32_memory_cycles', completed: 32, completed_known: true, at_ms: 32 })\n"
        "writeSync(1, 'published\\n')\n",
        encoding="utf-8",
    )
    directory = tmp_path / "owned-progress"
    process = subprocess.Popen(
        [_node(), str(script), str(directory)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    held = None
    try:
        ready = _wait_line(process.stdout, _TIMEOUT)
        if ready != b"ready\n":
            _fail_process(process)
        snapshot = directory / "01.json"
        held = snapshot.open("rb")
        old = held.read()
        assert json.loads(old)["phase"] == "16_memory_cycles"
        assert process.stdin is not None
        process.stdin.write(b"\n")
        process.stdin.close()
        published = _wait_line(process.stdout, _TIMEOUT)
        if published != b"published\n":
            _fail_process(process)
        try:
            code = process.wait(timeout=_TIMEOUT)
        except subprocess.TimeoutExpired:
            _fail_process(process)
            raise
        error = process.stderr.read() if process.stderr is not None else b""
        assert code == 0, error
        held.seek(0)
        assert held.read() == old
        assert read_owned_marker(tmp_path) == {
            "phase": "32_memory_cycles",
            "completed": 32,
            "completed_known": True,
            "at_ms": 32,
        }
        assert list(directory.glob("*.tmp")) == []
        assert (directory / "02.json").is_file()
    finally:
        if held is not None:
            held.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=_TIMEOUT)
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def test_noncanonical_digits_and_entry_bound_stay_unknown(tmp_path: Path):
    progress = tmp_path / "owned-progress"
    progress.mkdir()
    (tmp_path / "monitor.json").write_text(
        '{"phase":"finished","completed":128,"completed_known":true}',
        encoding="utf-8",
    )
    (progress / "\u0660\u0661.json").write_text(
        '{"phase":"finished","completed":128,"completed_known":true}',
        encoding="utf-8",
    )
    assert read_owned_marker(tmp_path) is None
    (progress / "\u0660\u0661.json").unlink()
    (progress / "\uff10\uff11.json").write_text(
        '{"phase":"16_memory_cycles","at_ms":16}',
        encoding="utf-8",
    )
    assert read_owned_marker(tmp_path) is None
    (progress / "\uff10\uff11.json").unlink()
    record = '{"phase":"measuring","at_ms":1}'
    for index in range(1, 65):
        (progress / f"{index:02d}.json").write_text(record, encoding="utf-8")
    (progress / "64.json.tmp").write_text("{", encoding="utf-8")
    assert read_owned_marker(tmp_path) is None
    (progress / "64.json.tmp").unlink()
    assert read_owned_marker(tmp_path) == {"phase": "measuring", "at_ms": 1}
    (progress / "64.json").write_bytes(b"{" + b"x" * 1024)
    assert read_owned_marker(tmp_path) is None


def test_symlink_snapshot_is_unknown(tmp_path: Path):
    progress = tmp_path / "owned-progress"
    progress.mkdir()
    target = tmp_path / "real.json"
    target.write_text('{"phase":"finished","completed":128,"completed_known":true}', encoding="utf-8")
    try:
        (progress / "01.json").symlink_to(target)
    except OSError:
        pytest.skip("symlink privilege")
    assert read_owned_marker(tmp_path) is None
