"""Private, versioned native agent runtimes with a stable OS launcher.

An AppImage's mount disappears when Studio closes. Copy the verified bundled
engine once, switch a small pointer on app updates, and retain running engines
until their OS process leases end. No model or runtime download is needed.
"""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import time
from uuid import uuid4

import psutil

from . import local_state
from .private_output import private_output

MAX_BYTES = 768 * 1024**2
NAME = re.compile(r"r-[0-9a-f]{32}")

POSIX_LAUNCHER = r"""#!/bin/sh
set -eu
agent_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
agent_lock="$agent_root/runtime-lock"
agent_try=0
until mkdir -m 700 "$agent_lock" 2>/dev/null; do
  agent_try=$((agent_try+1))
  [ "$agent_try" -lt 150 ] || { echo 'Mnemion is updating its agent runtime. Retry shortly.' >&2; exit 75; }
  sleep 0.1
done
trap 'rm -f "$agent_lock/owner"; rmdir "$agent_lock"' EXIT
printf '%s\n' "$$" > "$agent_lock/owner"
IFS= read -r agent_runtime < "$agent_root/runtime-current"
agent_hash=${agent_runtime#r-}
case "$agent_hash" in *[!0-9a-f]*|'') exit 1;; esac
[ "${#agent_hash}" -eq 32 ] && [ "$agent_runtime" = "r-$agent_hash" ] || exit 1
agent_directory="$agent_root/runtimes/$agent_runtime"
: > "$agent_directory/.lease-$$"
rm -f "$agent_lock/owner"
rmdir "$agent_lock"
trap - EXIT
exec "$agent_directory/mnemion-engine" "$@"
"""

WINDOWS_LAUNCHER = r"""param([Parameter(Mandatory=$true)][string]$CredentialFile, [string]$LegacySpace)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$lock = Join-Path $root 'runtime-lock'
$owned = $false
$lease = $null
try {
    for ($attempt = 0; $attempt -lt 150; $attempt++) {
        try { New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null; $owned = $true; break }
        catch { Start-Sleep -Milliseconds 100 }
    }
    if (-not $owned) { throw 'Mnemion is updating its agent runtime. Retry shortly.' }
    [IO.File]::WriteAllText((Join-Path $lock 'owner'), [string]$PID)
    $pointer = Join-Path $root 'runtime-current'
    if ((Get-Item -LiteralPath $pointer).Length -gt 100) { throw 'Invalid Mnemion runtime pointer.' }
    $runtime = [IO.File]::ReadAllText($pointer).Trim()
    if ($runtime -notmatch '^r-[0-9a-f]{32}$') { throw 'Invalid Mnemion runtime pointer.' }
    $directory = Join-Path (Join-Path $root 'runtimes') $runtime
    $lease = Join-Path $directory ('.lease-' + $PID)
    [IO.File]::WriteAllText($lease, '')
    Remove-Item -LiteralPath (Join-Path $lock 'owner')
    Remove-Item -LiteralPath $lock
    $owned = $false
    if ($CredentialFile.Contains('"') -or $CredentialFile.Contains("`n") -or $CredentialFile.Contains("`r")) { throw 'Invalid credential path.' }
    Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
public static class MnemionAgentPipe {
    static async Task Forward(Stream source, Stream target) {
        var buffer = new byte[65536];
        int size;
        while ((size = await source.ReadAsync(buffer, 0, buffer.Length)) != 0) {
            await target.WriteAsync(buffer, 0, size);
            await target.FlushAsync();
        }
    }
    public static int Run(ProcessStartInfo start, string directory) {
        start.RedirectStandardInput = true;
        start.RedirectStandardOutput = true;
        start.RedirectStandardError = true;
        using (var child = Process.Start(start)) {
            var lease = Path.Combine(directory, ".lease-" + child.Id);
            File.WriteAllText(lease, "");
            try {
                var input = Forward(Console.OpenStandardInput(), child.StandardInput.BaseStream);
                input.ContinueWith(task => { try { child.StandardInput.Close(); } catch {} });
                var output = Forward(child.StandardOutput.BaseStream, Console.OpenStandardOutput());
                var error = Forward(child.StandardError.BaseStream, Console.OpenStandardError());
                child.WaitForExit();
                Task.WaitAll(output, error);
                return child.ExitCode;
            } finally { if (child.HasExited) File.Delete(lease); }
        }
    }
}
'@
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = Join-Path $directory 'mnemion-engine.exe'
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.Arguments = '--credentials "' + $CredentialFile + '" mcp'
    if ($LegacySpace) {
        $parsed = [Guid]::Parse($LegacySpace)
        $start.Arguments += ' --legacy-space ' + $parsed.ToString()
    }
    $result = [MnemionAgentPipe]::Run($start, $directory)
} catch {
    [Console]::Error.WriteLine('Mnemion could not start its private agent runtime. Open Studio and review Agent connections on this computer.')
    $result = 1
} finally {
    if ($lease -and (Test-Path -LiteralPath $lease)) { Remove-Item -LiteralPath $lease -ErrorAction SilentlyContinue }
    if ($owned) {
        Remove-Item -LiteralPath (Join-Path $lock 'owner') -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $lock -ErrorAction SilentlyContinue
    }
}
exit $result
"""


def available(executable: Path) -> bool:
    return (executable.parent / "mnemion-runtime.json").is_file()


def bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError("Agent runtime record exceeds its limit")
    return value


def command(root: Path, credentials: Path, legacy_space=None) -> dict:
    if os.name == "nt":
        return {
            "command": str(
                Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            ),
            "args": [
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "RemoteSigned",
                "-File",
                str(root / "mnemion-agent.ps1"),
                "-CredentialFile",
                str(credentials),
            ]
            + (["-LegacySpace", str(legacy_space)] if legacy_space else []),
        }
    return {
        "command": str(root / "mnemion-agent.sh"),
        "args": ["--credentials", str(credentials), "mcp"]
        + (["--legacy-space", str(legacy_space)] if legacy_space else []),
    }


def publish(path: Path, value: bytes, *, executable=False) -> None:
    temporary = path.with_name(".runtime-write-" + uuid4().hex)
    try:
        with private_output(temporary) as stream:
            stream.write(value)
        if executable and os.name != "nt":
            temporary.chmod(0o700)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def runtime_lock(root: Path):
    path = root / "runtime-lock"
    deadline = time.monotonic() + 20
    while True:
        try:
            path.mkdir(mode=0o700)
            (path / "owner").write_text(str(os.getpid()), encoding="ascii")
            break
        except FileExistsError:
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
                raise ValueError("Invalid agent runtime lock")
            owner = path / "owner"
            try:
                value = bounded(owner, 20)
                if len(value) > 20 or not value.strip().isdigit():
                    raise ValueError("Invalid agent runtime owner")
                stale = not psutil.pid_exists(int(value))
            except FileNotFoundError:
                stale = time.time() - info.st_mtime > 60
            if stale:
                owner.unlink(missing_ok=True)
                path.rmdir()
                continue
            if time.monotonic() >= deadline:
                raise ValueError("Agent runtime is busy")
            time.sleep(0.1)
    try:
        yield
    finally:
        (path / "owner").unlink()
        path.rmdir()


def inventory(source: Path) -> tuple[dict, bytes, str]:
    path = source / "mnemion-runtime.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024**2:
        raise ValueError("Invalid bundled runtime inventory")
    raw = bounded(path, 4 * 1024**2)
    metadata = json.loads(raw)
    if not isinstance(metadata, dict):
        raise ValueError("Invalid bundled runtime inventory")
    files = metadata.get("files")
    if (
        metadata.get("format") != 1
        or metadata.get("component") != "service"
        or not isinstance(files, dict)
        or not 1 <= len(files) <= 10000
    ):
        raise ValueError("Invalid bundled runtime inventory")
    seen, total = set(), 0
    for name, entry in files.items():
        part = PurePosixPath(name)
        if (
            not name
            or part.is_absolute()
            or ".." in part.parts
            or ":" in name
            or "\\" in name
            or part.as_posix() != name
            or name.casefold() in seen
            or name == "mnemion-runtime.json"
        ):
            raise ValueError("Unsafe bundled runtime path")
        seen.add(name.casefold())
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("size"), int)
            or not 0 <= entry["size"] <= MAX_BYTES
            or not isinstance(entry.get("sha256"), str)
            or not re.fullmatch("[0-9a-f]{64}", entry.get("sha256", ""))
            or not isinstance(entry.get("executable"), bool)
        ):
            raise ValueError("Invalid bundled runtime file")
        total += entry["size"]
    executable = "mnemion-engine.exe" if os.name == "nt" else "mnemion-engine"
    if (
        total > MAX_BYTES
        or executable not in files
        or not isinstance(metadata.get("version"), str)
        or not re.fullmatch(r"\d+\.\d+\.\d+", metadata.get("version", ""))
    ):
        raise ValueError("Invalid bundled runtime bounds")
    return metadata, raw, "r-" + hashlib.sha256(raw).hexdigest()[:32]


def prepare(root: Path, executable: Path) -> str:
    """Caller holds the private setup lock; launchers share the brief publish lock."""
    source = executable.parent
    metadata, raw, name = inventory(source)
    for abandoned in root.glob("runtime-stage-*"):
        if (
            re.fullmatch(r"runtime-stage-[0-9a-f]{32}", abandoned.name)
            and abandoned.is_dir()
            and not abandoned.is_symlink()
        ):
            shutil.rmtree(abandoned)
    runtimes = local_state.directory(root / "runtimes")
    destination = runtimes / name
    if not destination.exists():
        total = sum(entry["size"] for entry in metadata["files"].values())
        if shutil.disk_usage(root).free < total + 64 * 1024**2:
            raise ValueError("Not enough space for the private agent runtime")
        stage = local_state.directory(root / ("runtime-stage-" + uuid4().hex), exist_ok=False)
        try:
            for relative, entry in metadata["files"].items():
                original, target = source / relative, stage / relative
                if (
                    original.is_symlink()
                    or not original.is_file()
                    or not original.resolve().is_relative_to(source.resolve())
                ):
                    raise ValueError("Unsafe bundled runtime file")
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                digest, size = hashlib.sha256(), 0
                with original.open("rb") as incoming, target.open("xb") as outgoing:
                    while block := incoming.read(1024 * 1024):
                        size += len(block)
                        if size > entry["size"]:
                            raise ValueError("Bundled runtime exceeds inventory size")
                        digest.update(block)
                        outgoing.write(block)
                if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise ValueError("Bundled runtime differs from its inventory")
                if os.name != "nt":
                    target.chmod(0o700 if entry["executable"] else 0o600)
            (stage / "mnemion-runtime.json").write_bytes(raw)
            stage.rename(destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    elif (
        destination.is_symlink()
        or bounded(destination / "mnemion-runtime.json", 4 * 1024**2) != raw
    ):
        raise ValueError("The private runtime inventory has changed")
    script = root / ("mnemion-agent.ps1" if os.name == "nt" else "mnemion-agent.sh")
    content = (WINDOWS_LAUNCHER if os.name == "nt" else POSIX_LAUNCHER).encode("utf-8")
    with runtime_lock(root):
        pointer = root / "runtime-current"
        previous = bounded(pointer, 100).decode("ascii").strip() if pointer.exists() else None
        if script.is_symlink() or (script.exists() and not script.is_file()):
            raise ValueError("Invalid private launcher path")
        if not script.exists() or bounded(script, 16384) != content:
            publish(script, content, executable=True)
        if previous != name:
            publish(pointer, (name + "\n").encode("ascii"))
        for candidate in runtimes.iterdir():
            if (
                candidate.name in {name, previous}
                or not NAME.fullmatch(candidate.name)
                or candidate.is_symlink()
                or not candidate.is_dir()
            ):
                continue
            # The launcher holds this lock until its lease exists. A live
            # process keeps its exact immutable files through later updates.
            if any(
                lease.name[7:].isdigit() and psutil.pid_exists(int(lease.name[7:]))
                for lease in candidate.glob(".lease-*")
            ):
                continue
            shutil.rmtree(candidate)
    return metadata["version"]


def current_version(root: Path) -> str | None:
    try:
        name = bounded(root / "runtime-current", 100).decode("ascii").strip()
        if not NAME.fullmatch(name):
            return None
        return json.loads(bounded(root / "runtimes" / name / "mnemion-runtime.json", 4 * 1024**2))[
            "version"
        ]
    except (OSError, ValueError, KeyError):
        return None
