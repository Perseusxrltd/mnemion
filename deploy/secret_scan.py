"""Pinned, free secret scans with bounded, redacted release evidence.

Source mode scans a private snapshot of tracked and unignored source files.
Path mode also inspects supported archives to depth four and encoded text to
depth five. Executable internals and encrypted content are not decompiled.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid
import zipfile

VERSION = "8.30.1"
ARCHIVES = {
    "linux_x64.tar.gz": "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
    "linux_arm64.tar.gz": "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080",
    "darwin_x64.tar.gz": "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709",
    "darwin_arm64.tar.gz": "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
    "windows_x64.zip": "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e",
    "windows_arm64.zip": "b95f5e4f5c425cedca7ee203d9afd29597e692c4924a12ed42f970537c72cc0f",
}
MAX_DOWNLOAD = 32 * 1024**2
MAX_REPORT = 16 * 1024**2
MAX_EXPANSION = 8 * 1024**3
ROOT = Path(__file__).resolve().parents[1]
PROCESS_ENVIRONMENT = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "HOME",
    "USERPROFILE",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "TZ",
    "LOCALAPPDATA",
    "APPDATA",
}


class ScanError(RuntimeError):
    """Fixed diagnostics only; never print scanner input or matched content."""


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def process_environment():
    return {
        name: value for name, value in os.environ.items() if name.upper() in PROCESS_ENVIRONMENT
    }


def archive_name():
    system = platform.system().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine().lower()
    )
    suffix = "zip" if system == "windows" else "tar.gz"
    name = f"{system}_{arch}.{suffix}"
    if name not in ARCHIVES:
        raise ScanError("Secret scanning requires a supported x64 or arm64 build host")
    return name


def executable_bytes(data, name):
    expected = "gitleaks.exe" if name.startswith("windows_") else "gitleaks"
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            matches = [entry for entry in archive.infolist() if entry.filename == expected]
            if len(matches) != 1:
                raise ScanError("Pinned scanner archive has an unexpected executable")
            entry = matches[0]
            if (
                stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
                or not 0 < entry.file_size <= MAX_DOWNLOAD
            ):
                raise ScanError("Pinned scanner executable is not a bounded regular file")
            return archive.read(entry)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        matches = [entry for entry in archive.getmembers() if entry.name == expected]
        if len(matches) != 1 or not matches[0].isfile() or not 0 < matches[0].size <= MAX_DOWNLOAD:
            raise ScanError("Pinned scanner executable is not a bounded regular file")
        with archive.extractfile(matches[0]) as stream:
            return stream.read(MAX_DOWNLOAD + 1)


@contextmanager
def scanner(cache):
    name = archive_name()
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    archive = cache / f"gitleaks_{VERSION}_{name}"
    if archive.is_symlink():
        raise ScanError("Scanner cache must not contain linked archives")
    if not archive.exists():
        url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/{archive.name}"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(MAX_DOWNLOAD + 1)
        if len(data) > MAX_DOWNLOAD or hashlib.sha256(data).hexdigest() != ARCHIVES[name]:
            raise ScanError("Scanner download did not match the pinned digest")
        temporary = archive.with_name(archive.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    if (
        not archive.is_file()
        or archive.stat().st_size > MAX_DOWNLOAD
        or digest(archive) != ARCHIVES[name]
    ):
        raise ScanError("Cached scanner archive did not match the pinned digest")
    with tempfile.TemporaryDirectory(prefix="scanner-", dir=cache) as directory:
        executable = Path(directory) / ("gitleaks.exe" if os.name == "nt" else "gitleaks")
        executable.write_bytes(executable_bytes(archive.read_bytes(), name))
        executable.chmod(0o700)
        result = subprocess.run(
            [str(executable), "version"],
            capture_output=True,
            text=True,
            timeout=10,
            env=process_environment(),
        )
        if result.returncode or result.stdout.strip() != VERSION:
            raise ScanError("The pinned scanner did not report the expected version")
        yield (
            executable,
            {
                "version": VERSION,
                "archive_sha256": ARCHIVES[name],
                "executable_sha256": digest(executable),
            },
        )


def source_paths(root):
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
        timeout=30,
    )
    paths = []
    for name in sorted(set(result.stdout.decode("utf-8").split("\0")) - {""}):
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ScanError("Source scan encountered an unsafe path")
        path = root / relative
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(root.resolve())
        ):
            raise ScanError("Source scan requires regular files inside the repository")
        paths.append(path)
    if not paths:
        raise ScanError("Source scan cannot accept an empty inventory")
    return paths


def inventory(paths):
    result = {}
    for number, target in enumerate(paths):
        if target.is_symlink() or not target.exists():
            raise ScanError("Secret scan input is missing or linked")
        for path in sorted(target.rglob("*")) if target.is_dir() else [target]:
            if path.is_symlink():
                raise ScanError("Secret scan requires unlinked distribution inputs")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ScanError("Secret scan requires regular files")
            relative = path.relative_to(target) if target.is_dir() else Path(target.name)
            result[f"{number}/{relative.as_posix()}"] = {
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
    if not result:
        raise ScanError("Secret scan cannot accept empty inputs")
    return result


def scan_input(paths, output):
    """Flatten bounded archive contents; filenames cannot invoke scanner skips.

    In particular Gitleaks does not recognize wheels as ZIP containers by suffix.
    No archive path is extracted or executed, and archive links are never followed.
    """
    total, entries, line = 0, 0, 1
    locations = []
    expires = time.monotonic() + 300

    def write(data):
        nonlocal total, line
        total += len(data)
        if total > MAX_EXPANSION or time.monotonic() >= expires:
            raise ScanError("Secret scan expansion exceeded its byte or time budget")
        output.write(data)
        line += data.count(b"\n")

    def member(stream, name, depth=0, label=None):
        nonlocal entries
        entries += 1
        if entries > 100000:
            raise ScanError("Secret scan exceeded its file inventory budget")
        archive_kind = (
            "zip"
            if name.lower().endswith((".zip", ".whl"))
            else "tar"
            if name.lower().endswith((".tar.gz", ".tgz"))
            else None
        )
        if archive_kind:
            if depth >= 4:
                raise ScanError("Secret scan encountered an archive beyond its depth budget")
            # A nested ZipExtFile/Tar member need not be seekable. Spool bounded
            # archive bytes to private disk; never hold a large wheel in RAM.
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024**2) as packed:
                size = 0
                while data := stream.read(1024**2):
                    size += len(data)
                    if size > MAX_EXPANSION or time.monotonic() >= expires:
                        raise ScanError("Secret scan archive exceeded its byte or time budget")
                    packed.write(data)
                packed.seek(0)
                if archive_kind == "zip":
                    with zipfile.ZipFile(packed) as archive:
                        if len(archive.infolist()) + entries > 100000:
                            raise ScanError("Secret scan archive has too many entries")
                        member(
                            io.BytesIO(archive.comment),
                            "comment.txt",
                            depth + 1,
                            f"{label}!comment",
                        )
                        for entry in archive.infolist():
                            if entry.is_dir():
                                continue
                            if entry.flag_bits & 1 or entry.file_size > MAX_EXPANSION - total:
                                raise ScanError(
                                    "Secret scan cannot inspect an encrypted or oversized archive member"
                                )
                            with archive.open(entry) as child:
                                # ZIP links contain their target text, not data
                                # from the linked host path. Inspect that text.
                                linked = stat.S_ISLNK(entry.external_attr >> 16)
                                member(
                                    child,
                                    "link.txt" if linked else entry.filename,
                                    depth + 1,
                                    f"{label}!{entry.filename}",
                                )
                else:
                    with tarfile.open(fileobj=packed, mode="r:gz") as archive:
                        seen = 0
                        for entry in archive:
                            seen += 1
                            if seen > 100000 or time.monotonic() >= expires:
                                raise ScanError(
                                    "Secret scan archive exceeded its entry or time budget"
                                )
                            if entry.isfile():
                                if entry.size > MAX_EXPANSION - total:
                                    raise ScanError(
                                        "Secret scan archive member exceeds its byte budget"
                                    )
                                with archive.extractfile(entry) as child:
                                    member(child, entry.name, depth + 1, f"{label}!{entry.name}")
                            elif entry.issym() or entry.islnk():
                                member(
                                    io.BytesIO(entry.linkname.encode("utf-8")),
                                    "link.txt",
                                    depth + 1,
                                    f"{label}!{entry.name}",
                                )
                            elif not entry.isdir():
                                raise ScanError(
                                    "Secret scan cannot inspect this archive entry type"
                                )
        else:
            first = line
            while data := stream.read(1024**2):
                write(data)
            write(b"\n")
            locations.append({"member": label, "first_line": first, "last_line": line - 1})

    # Gitleaks also skips a complete stdin stream when its initial bytes look
    # like an executable. A fixed text prelude with a newline prevents this
    # content-type shortcut while preserving every input byte for inspection.
    write(b"Mnemion bounded secret-scan stream\n")
    for path in paths:
        for file in sorted(path.rglob("*")) if path.is_dir() else [path]:
            if file.is_file():
                with file.open("rb") as stream:
                    member(stream, file.name, label=str(file))
    output.seek(0)
    return {"inspected_stream_bytes": total, "inspected_members": entries, "locations": locations}


def run_scanner(executable, rules, paths, evidence):
    evidence.mkdir(mode=0o700, parents=True)
    # Explicitly empty ignores and fixed rules prevent environment variables,
    # inline allow comments or an unrelated .gitleaksignore from disabling gates.
    ignored = evidence / "empty.ignore"
    ignored.write_text("")
    env = process_environment()
    report, log = evidence / "0.private.json", evidence / "0.private.log"
    with tempfile.TemporaryFile(dir=evidence) as content:
        observed = scan_input(paths, content)
        # Full releases contain several gigabytes. Keep a finite deadline that
        # scales to their measured size rather than applying a source-only
        # timeout to all six platform distributions on a small runner.
        observed["scanner_timeout_seconds"] = min(
            1200, max(300, 60 + observed["inspected_stream_bytes"] // (4 * 1024**2))
        )
        (evidence / "stream-locations.private.json").write_text(
            json.dumps(observed.pop("locations"), indent=2) + "\n", encoding="utf-8"
        )
        command = [
            str(executable),
            "stdin",
            "--config",
            str(rules),
            "--gitleaks-ignore-path",
            str(ignored),
            "--ignore-gitleaks-allow",
            "--no-banner",
            "--no-color",
            "--redact=100",
            "--max-archive-depth",
            "4",
            "--max-decode-depth",
            "5",
            "--max-target-megabytes",
            "0",
            "--report-format",
            "json",
            "--report-path",
            str(report),
        ]
        with log.open("xb") as output:
            try:
                result = subprocess.run(
                    command,
                    stdin=content,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=env,
                    timeout=observed["scanner_timeout_seconds"],
                )
            except subprocess.TimeoutExpired:
                raise ScanError(
                    "Secret scan exceeded its deadline; publication remains blocked"
                ) from None
        if not report.is_file() or report.stat().st_size > MAX_REPORT:
            raise ScanError("Secret scan did not produce a bounded complete report")
        findings = json.loads(report.read_text(encoding="utf-8"))
        if not isinstance(findings, list) or result.returncode not in (0, 1):
            raise ScanError("Secret scan failed; publication remains blocked")
        if result.returncode or findings:
            raise ScanError(
                "Secret scan found possible credentials; inspect the private redacted report"
            )
    return {"findings": 0, **observed}


def canary(executable, rules, directory):
    """Reject archived, binary and encoded keys beside reviewed public metadata."""
    package = directory / "canary.zip"
    native = directory / "canary.bin"
    native.write_bytes(
        b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 56 + b"\naccess = mnm_" + b"B8f" * 14 + b"q\n"
    )
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as archive:
        archive.writestr("application.txt", "token = mnm_" + "A9b" * 14 + "x # gitleaks:allow\n")
        archive.writestr("vault.txt", "recovery = mnv_" + "X7y" * 14 + "z\n")
        archive.writestr(
            "annotation.txt",
            "private_key: x25519.X25519PrivateKey; token = mnm_" + "C6d" * 14 + "p\n",
        )
        metadata = {
            "013_oauth_bindings.sql": "9539cddc5ffa9587f192aed9fbe94dd1e92a26ac70233511dbaf86210cee2116",
            "token": "mnm_" + "E5f" * 14 + "n",
        }
        archive.writestr(
            "encoded-metadata.json",
            json.dumps({"payload": base64.b64encode(json.dumps(metadata).encode()).decode()}),
        )
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("synthetic-1.0-py3-none-any.whl", nested.getvalue())
    evidence = directory / "canary-evidence"
    try:
        run_scanner(executable, rules, [native, package], evidence)
    except ScanError:
        report = evidence / "0.private.json"
        if report.is_file() and report.stat().st_size <= MAX_REPORT:
            findings = json.loads(report.read_text(encoding="utf-8"))
            if isinstance(findings, list):
                rules_found = [
                    finding.get("RuleID") for finding in findings if isinstance(finding, dict)
                ]
                if (
                    rules_found.count("mnemion-application-or-backup-key") >= 4
                    and "mnemion-vault-key" in rules_found
                ):
                    return
    raise ScanError("Secret scanner canary did not reject every synthetic key placement")


def scan(root, paths, output, cache, *, source=False):
    output = output.resolve()
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    evidence = output.parent / f"{output.stem}-evidence-{stamp}"
    rules = root / ".gitleaks.toml"
    cache.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    originals = source_paths(root) if source else [path.absolute() for path in paths]
    before = inventory(originals)
    record = {
        "format": 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "passed": False,
        "scope": "source_snapshot" if source else "distribution_paths",
        "files": len(before),
        "bytes": sum(item["bytes"] for item in before.values()),
        "inventory_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        "rules_sha256": digest(rules),
        "implementation_sha256": digest(Path(__file__)),
        "archive_depth": 4,
        "decode_depth": 5,
        "max_file_size_skips": False,
        "filename_exclusions": False,
        "portable_archives_expanded": ["zip", "whl", "tar.gz", "tgz"],
        "executable_internals_decompiled": False,
        "encrypted_content_decrypted": False,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="secret-source-", dir=cache.parent) as temporary:
            inputs = originals
            if source:
                snapshot = Path(temporary)
                for path in originals:
                    target = snapshot / path.relative_to(root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
                inputs = [snapshot]
            if any(output.is_relative_to(path) for path in inputs if path.is_dir()):
                raise ScanError("Secret scan reports must be outside scanned directories")
            with scanner(cache) as (executable, identity):
                record["scanner"] = identity
                with tempfile.TemporaryDirectory(
                    prefix="scan-canary-", dir=cache.parent
                ) as control:
                    canary(executable, rules, Path(control))
                record["archived_key_canary_passed"] = True
                record["binary_first_key_canary_passed"] = True
                record["annotation_adjacent_key_canary_passed"] = True
                record["decoded_metadata_key_canary_passed"] = True
                record.update(run_scanner(executable, rules, inputs, evidence))
            if inventory(originals) != before or digest(rules) != record["rules_sha256"]:
                raise ScanError("Secret scan inputs changed during inspection")
            record["passed"] = True
    finally:
        if output.exists():
            output.replace(output.with_name(output.name + ".previous-" + stamp))
        output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", action="store_true")
    mode.add_argument("--paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=ROOT / ".tmp/secret-scan-tools")
    args = parser.parse_args()
    args.cache.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        record = scan(ROOT, args.paths or [], args.output, args.cache, source=args.source)
    except ScanError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("Secret scan could not complete; publication remains blocked", file=sys.stderr)
        return 1
    print(json.dumps(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
