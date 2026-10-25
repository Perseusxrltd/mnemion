"""Check the actual release-owned network probe, without creating telemetry."""

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


def probe(artifact: Path, *, node: str | None = None) -> dict:
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
    result = {
        "schema_version": 1,
        "platform": operating_system,
        "architecture": sorted(target[1]),
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "python": {"version": platform.python_version(), "flags": value, "seconds": elapsed},
        "qualification": "component only; not installed or whole-feature resource acceptance",
    }
    if node:
        command = shutil.which(node)
        if not command:
            raise ValueError("The requested Node runtime is unavailable")
        program = """
const before=process.memoryUsage().rss, started=performance.now();
const binding=require(process.argv[1]);
if(Object.keys(binding).join()!=='readState') throw new Error('Unexpected native ABI');
binding.readState().then(flags=>{
  const seconds=(performance.now()-started)/1000;
  if(![0,8,9,10,12,13,14].includes(flags)||seconds>=1) throw new Error('Native probe failed');
  console.log(JSON.stringify({version:process.versions.node,electron:process.versions.electron??null,
    flags,seconds,added_rss_bytes:process.memoryUsage().rss-before}));
});
"""
        child = subprocess.run(
            [command, "-e", program, str(artifact)],
            capture_output=True,
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = probe(args.artifact, node=args.node)
    body = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(body)
    print(body, end="")


if __name__ == "__main__":
    main()
