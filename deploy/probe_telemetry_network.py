"""Check release-owned network/aggregate CPU admission, without creating telemetry."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from deploy.native_resources import binary_target

FLAGS = {0, 8, 9, 10, 12, 13, 14}


class CpuTotals(ctypes.Structure):
    _fields_ = [("idle", ctypes.c_uint64), ("total", ctypes.c_uint64), ("count", ctypes.c_uint32)]


class ReviewClock(ctypes.Structure):
    _fields_ = [("elapsed_ms", ctypes.c_uint64), ("epoch", ctypes.c_ubyte * 16)]


def probe(artifact: Path, *, node: str | None = None, initialize_review_clock=False) -> dict:
    artifact = artifact.resolve(strict=True)
    target = binary_target(artifact)
    operating_system = {"win32": "windows", "darwin": "macos", "linux": "linux"}[sys.platform]
    if target is None or target[0] != operating_system:
        raise ValueError("The probe belongs to a different operating system")
    interpreter = binary_target(Path(sys.executable))
    if interpreter is None or not target[1].intersection(interpreter[1]):
        raise ValueError("Use a matching interpreter to qualify the C ABI")
    started = time.monotonic()
    library = ctypes.CDLL(str(artifact))
    function = library.mnemion_network_state_v1
    function.argtypes = []
    function.restype = ctypes.c_uint32
    value = function()
    elapsed = time.monotonic() - started
    if value not in FLAGS or elapsed >= 1:
        raise ValueError("The actual C probe failed its flag/deadline contract")
    cpu = CpuTotals()
    read_cpu = library.mnemion_cpu_totals_v1
    read_cpu.argtypes = [ctypes.POINTER(CpuTotals)]
    read_cpu.restype = ctypes.c_int
    available = read_cpu(ctypes.byref(cpu))
    if (
        available not in (0, 1)
        or (
            available
            and not (
                0 <= cpu.idle <= cpu.total <= 9007199254740991
                and cpu.total > 0
                and 0 < cpu.count <= 1048576
            )
        )
        or (not available and (cpu.idle or cpu.total or cpu.count))
    ):
        raise ValueError("The actual aggregate CPU probe returned invalid counters")
    clock = ReviewClock()
    read_clock = library.mnemion_review_clock_v1
    read_clock.argtypes = [ctypes.c_int, ctypes.POINTER(ReviewClock)]
    read_clock.restype = ctypes.c_int
    clock_available = read_clock(int(initialize_review_clock), ctypes.byref(clock))
    if (
        clock_available not in (0, 1)
        or (clock_available and (clock.elapsed_ms > 9007199254740991 or not any(clock.epoch)))
        or (not clock_available and (clock.elapsed_ms or any(clock.epoch)))
    ):
        raise ValueError("The actual review clock returned invalid control state")
    from mnemion.product_telemetry.review_clock_system import read_system_review_clock

    # The compiler-free package path must share the exact native epoch/timebase.
    # It is read-only here, including when C explicitly initialized Windows.
    system_clock = read_system_review_clock()
    shared_system_clock = bool(
        clock_available
        and system_clock
        and system_clock["epoch"] == bytes(clock.epoch).hex()
        and system_clock["elapsed_ms"] >= clock.elapsed_ms
    )
    if bool(system_clock) != bool(clock_available) or (clock_available and not shared_system_clock):
        raise ValueError("The source-install review clock does not match the packaged helper")
    result = {
        "schema_version": 1,
        "platform": operating_system,
        "architecture": sorted(target[1]),
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "probe_scope": "network_cpu_and_review_clock",
        "review_clock_initialization_requested": initialize_review_clock,
        "python": {
            "version": platform.python_version(),
            "flags": value,
            "seconds": elapsed,
            "aggregate_cpu_available": bool(available),
            "review_clock_available": bool(clock_available),
            "system_review_clock_available": bool(system_clock),
            "system_review_clock_matches_helper": shared_system_clock,
        },
        "qualification": "component only; not installed or whole-feature resource acceptance",
    }
    if node:
        command = shutil.which(node)
        if not command:
            raise ValueError("The requested Node runtime is unavailable")
        program = """
const before=process.memoryUsage().rss, started=performance.now();
const binding=require(process.argv[1]);
if(Object.keys(binding).sort().join()!=='initializeReviewClock,readCpuTotals,readReviewClock,readState') throw new Error('Unexpected native ABI');
binding.readState().then(flags=>{
  const seconds=(performance.now()-started)/1000;
  if(![0,8,9,10,12,13,14].includes(flags)||seconds>=1) throw new Error('Native probe failed');
  const cpu=binding.readCpuTotals();
  if(!Array.isArray(cpu)||(cpu.length!==0&&(cpu.length!==3||
    cpu.some(value=>!Number.isSafeInteger(value)||value<0)||cpu[0]>cpu[1]||cpu[1]===0||cpu[2]===0||cpu[2]>1048576)))
    throw new Error('Aggregate CPU probe failed');
  const clock=binding.readReviewClock();
  if(!Array.isArray(clock)||(clock.length!==0&&(clock.length!==2||
    !Number.isSafeInteger(clock[0])||clock[0]<0||typeof clock[1]!=='string'||
    !/^[0-9a-f]{32}$/.test(clock[1])||/^0+$/.test(clock[1])))) throw new Error('Review clock failed');
  const previous=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
  if(previous&&(clock.length!==2||clock[1]!==previous.epoch||clock[0]<previous.elapsed_ms))
    throw new Error('Review clocks are not comparable across runtimes');
  console.log(JSON.stringify({version:process.versions.node,electron:process.versions.electron??null,
    flags,seconds,aggregate_cpu_available:cpu.length===3,review_clock_available:clock.length===2,
    review_clock_shared_across_runtimes:Boolean(previous),added_rss_bytes:process.memoryUsage().rss-before}));
});
"""
        child = subprocess.run(
            [command, "-e", program, str(artifact)],
            capture_output=True,
            input=json.dumps(
                {"epoch": bytes(clock.epoch).hex(), "elapsed_ms": clock.elapsed_ms}
                if clock_available
                else None
            ),
            text=True,
            check=True,
            timeout=5,
        )
        result["node"] = json.loads(child.stdout)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--node")
    parser.add_argument(
        "--initialize-review-clock",
        action="store_true",
        help="Initialize the Windows volatile review marker for this component check",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = probe(
        args.artifact, node=args.node, initialize_review_clock=args.initialize_review_clock
    )
    body = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(body)
    print(body, end="")


if __name__ == "__main__":
    main()
