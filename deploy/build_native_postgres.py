"""Build a relocatable database for app-managed local workspaces.

Only release builders need a compiler. Sources and licenses are pinned; binaries
use the baseline CPU instruction set and static current OpenSSL/zlib. This does
not install a service or touch an existing database on the builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sysconfig
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("postgresql", "pgvector", "zlib", "openssl")
LIMIT = 128 * 1024 * 1024


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(spec: dict, cache: Path) -> Path:
    checksum = spec["sha256"]
    if not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid pinned source digest")
    url = spec["url"]
    if not url.startswith(
        (
            "https://ftp.postgresql.org/pub/source/",
            "https://codeload.github.com/pgvector/pgvector/tar.gz/",
            "https://github.com/madler/zlib/releases/download/",
            "https://github.com/openssl/openssl/releases/download/",
            "https://github.com/lexxmark/winflexbison/releases/download/",
        )
    ):
        raise ValueError("Unexpected native runtime source publisher")
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / checksum
    if target.exists():
        if (
            not target.is_file()
            or target.is_symlink()
            or target.stat().st_size > LIMIT
            or digest(target) != checksum
        ):
            raise ValueError("Cached source does not match its pinned digest")
        return target
    request = urllib.request.Request(url, headers={"User-Agent": "Mnemion-native-builder"})
    temporary = target.with_suffix(".download")
    try:
        with urllib.request.urlopen(request, timeout=30) as response, temporary.open("xb") as out:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > LIMIT:
                    raise ValueError("Native runtime source exceeds its size budget")
                out.write(chunk)
        if digest(temporary) != checksum:
            raise ValueError("Native runtime source differs from its pinned digest")
        temporary.rename(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def extract(source: Path, destination: Path, prefix: str | None) -> Path:
    """No links, special entries, traversal or unbounded source expansion."""
    destination.mkdir()
    seen: set[str] = set()

    def path_ok(name: str) -> bool:
        parts = PurePosixPath(name).parts
        normalized = "/".join(parts).casefold()
        allowed = bool(parts) and not (
            name.startswith("/")
            or "\\" in name
            or ":" in name
            or ".." in parts
            or (prefix is not None and parts[0] != prefix)
            or normalized in seen
        )
        seen.add(normalized)
        return allowed

    if prefix is None:
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > 40000 or sum(e.file_size for e in entries) > 512 * 1024**2:
                raise ValueError("Build source exceeds its expanded budget")
            if any(not path_ok(e.filename) or stat.S_ISLNK(e.external_attr >> 16) for e in entries):
                raise ValueError("Unsafe build source archive")
            archive.extractall(destination)
        return destination
    with tarfile.open(source) as archive:
        entries = archive.getmembers()
        if len(entries) > 40000 or sum(e.size for e in entries) > 512 * 1024**2:
            raise ValueError("Build source exceeds its expanded budget")
        if any(not path_ok(e.name) or not (e.isfile() or e.isdir()) for e in entries):
            raise ValueError("Unsafe build source archive")
        archive.extractall(destination, filter="data")
    return destination / prefix


def host_target() -> tuple[str, str]:
    operating_system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}.get(
        platform.system()
    )
    architecture = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine().lower()
    )
    if not operating_system or not architecture:
        raise ValueError("Unsupported native database build target")
    if operating_system == "windows" and architecture != "x64":
        raise ValueError("Build Windows x64 natively; validate its separate ARM emulation gate")
    return operating_system, architecture


def native_files(directory: Path, operating_system: str) -> list[Path]:
    magic = {
        "linux": {b"\x7fELF"},
        "macos": {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe"},
        "windows": {b"MZ"},
    }[operating_system]
    result = []
    for path in directory.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            start = stream.read(4)
        if start in magic or start[:2] in magic:
            result.append(path)
    return result


def relocate_macos(directory: Path) -> None:
    files = native_files(directory, "macos")
    for path in files:
        listing = subprocess.check_output(["otool", "-L", str(path)], text=True)
        for row in listing.splitlines()[1:]:
            dependency = row.strip().split(" (compatibility version ", 1)[0]
            if dependency.startswith(str(directory) + "/"):
                relative = os.path.relpath(dependency, path.parent).replace(os.sep, "/")
                subprocess.run(
                    [
                        "install_name_tool",
                        "-change",
                        dependency,
                        "@loader_path/" + relative,
                        str(path),
                    ],
                    check=True,
                )
        identity = subprocess.check_output(["otool", "-D", str(path)], text=True).splitlines()
        if len(identity) == 2:
            subprocess.run(
                ["install_name_tool", "-id", "@rpath/" + path.name, str(path)], check=True
            )
        subprocess.run(
            ["codesign", "--force", "--sign", "-", "--timestamp=none", str(path)], check=True
        )
        subprocess.run(["codesign", "--verify", "--strict", str(path)], check=True)


def inspect(directory: Path, operating_system: str) -> dict[str, list[str]]:
    result = {}
    unavailable = {}
    for path in native_files(directory, operating_system):
        if operating_system == "linux":
            listing = subprocess.check_output(["readelf", "-d", str(path)], text=True)
            libraries = re.findall(r"\(NEEDED\).*\[([^\]]+)\]", listing)
            allowed = {
                "libc.so.6",
                "libm.so.6",
                "libdl.so.2",
                "libpthread.so.0",
                "librt.so.1",
                "libresolv.so.2",
                "libpq.so.5",
                "libecpg.so.6",
                "libecpg_compat.so.3",
                "libpgtypes.so.3",
                "ld-linux-aarch64.so.1",
                "ld-linux-x86-64.so.2",
            }
            if any(lib not in allowed for lib in libraries):
                raise ValueError(f"Unexpected native dependency in {path.name}: {libraries}")
            paths = re.findall(r"\((?:RUNPATH|RPATH)\).*\[([^\]]+)\]", listing)
            if any(not p.startswith("$ORIGIN") for value in paths for p in value.split(":")):
                raise ValueError("Database binary contains a non-relocatable library path")
        elif operating_system == "macos":
            listing = subprocess.check_output(["otool", "-L", str(path)], text=True)
            libraries = [
                line.strip().split(" (compatibility version ", 1)[0]
                for line in listing.splitlines()[1:]
            ]
            if any(
                not lib.startswith(("@loader_path/", "@rpath/", "/usr/lib/", "/System/Library/"))
                for lib in libraries
            ):
                raise ValueError(f"Unexpected native dependency in {path.name}: {libraries}")
        else:
            listing = subprocess.check_output(["dumpbin", "/DEPENDENTS", str(path)], text=True)
            libraries = re.findall(r"^\s+([\w.-]+\.dll)\s*$", listing, re.I | re.M)
            external = [
                lib
                for lib in libraries
                if (
                    "vcruntime" in lib.lower()
                    or "msvcp" in lib.lower()
                    or "libssl" in lib.lower()
                    or "libcrypto" in lib.lower()
                    or "zlib" in lib.lower()
                )
            ]
            if external:
                unavailable[path.relative_to(directory).as_posix()] = external
        result[path.relative_to(directory).as_posix()] = libraries
    if unavailable:
        raise ValueError(
            "The Windows runtime requires unbundled redistributables: "
            + json.dumps(unavailable, sort_keys=True)
        )
    if not result:
        raise ValueError("No native database binaries were built")
    return result


def build(output: Path, cache: Path, work: Path) -> Path:
    operating_system, architecture = host_target()
    configuration = json.loads((ROOT / "deploy/native-postgres.json").read_text())
    if configuration["format"] != 1:
        raise ValueError("Unsupported native source manifest")
    if work.exists():
        raise ValueError("Use a new build directory; never overwrite an existing runtime")
    work.mkdir(parents=True)
    sources = {
        name: extract(
            fetch(configuration[name], cache),
            work / (name + "-source"),
            configuration[name]["root"],
        )
        for name in COMPONENTS
    }
    # PostgreSQL's substring check treats pthread_exit from static OpenSSL as
    # process exit. Permit thread termination and Apple's cleanup registration
    # while retaining checks for exit/_exit and other unapproved exit calls.
    if operating_system != "windows":
        check = sources["postgresql"] / "src/interfaces/libpq/Makefile"
        original = check.read_text()
        marker = "grep -v -e __cxa_atexit -e __tsan_func_exit"
        if original.count(marker) != 1:
            raise ValueError("Review the upstream libpq symbol check before updating sources")
        allowed = " -e pthread_exit"
        if operating_system == "macos":
            # Make needs $$ to pass the end anchor through to the shell.
            allowed += " -e ' _atexit$$'"
        check.write_text(original.replace(marker, marker + allowed))
    else:
        check = sources["postgresql"] / "meson.build"
        original = check.read_text()
        marker = "ssl = dependency('openssl', required: false)"
        if original.count(marker) != 1:
            raise ValueError("Review upstream OpenSSL discovery before updating sources")
        # Static OpenSSL needs its private system dependencies. A global
        # prefer_static option incorrectly asks for static Windows OS libraries.
        check.write_text(
            original.replace(
                marker,
                "ssl = dependency('openssl', required: false, static: true, method: 'pkg-config')",
            )
        )
    install, dependencies = work / "postgres", work / "dependencies"
    environment = dict(os.environ)
    environment["CFLAGS"] = "-O2 -fPIC -fno-omit-frame-pointer"
    environment["CXXFLAGS"] = environment["CFLAGS"]
    environment["LDFLAGS"] = ""
    if operating_system == "macos":
        environment["MACOSX_DEPLOYMENT_TARGET"] = "13.0"
        environment["CFLAGS"] += " -mmacosx-version-min=13.0"
    if operating_system == "windows":
        environment.pop("CFLAGS", None)
        environment.pop("CXXFLAGS", None)

    def run(command, cwd=work, timeout=1800):
        subprocess.run(
            [str(v) for v in command], cwd=cwd, env=environment, check=True, timeout=timeout
        )

    if operating_system == "windows":
        run(
            ["nmake", "/f", "win32/Makefile.msc", "CFLAGS=/nologo /MT /O2", "zlib.lib"],
            sources["zlib"],
        )
        (dependencies / "lib").mkdir(parents=True)
        (dependencies / "include").mkdir()
        shutil.copy2(sources["zlib"] / "zlib.lib", dependencies / "lib")
        for name in ("zlib.h", "zconf.h"):
            shutil.copy2(sources["zlib"] / name, dependencies / "include")
    else:
        run(["sh", "./configure", "--static", "--prefix=" + str(dependencies)], sources["zlib"])
        run(["make", "-j2"], sources["zlib"])
        run(["make", "install"], sources["zlib"])

    ssl_target = {
        ("linux", "x64"): "linux-x86_64",
        ("linux", "arm64"): "linux-aarch64",
        ("macos", "x64"): "darwin64-x86_64-cc",
        ("macos", "arm64"): "darwin64-arm64-cc",
        ("windows", "x64"): "VC-WIN64A",
    }[operating_system, architecture]
    flags = ["no-shared", "no-tests", "no-module", "--prefix=" + str(dependencies), "--libdir=lib"]
    if operating_system == "windows":
        flags += ["no-asm", "-MT"]
    else:
        flags += ["-fPIC"]
    run(["perl", "./Configure", ssl_target, *flags], sources["openssl"])
    make = ["nmake"] if operating_system == "windows" else ["make", "-j2"]
    run(make, sources["openssl"])
    run([make[0], "install_sw"], sources["openssl"])

    if operating_system == "windows":
        programs = {}
        for tool in ("meson", "ninja", "pkgconf"):
            program = Path(sysconfig.get_path("scripts")) / (tool + ".exe")
            programs[tool] = str(program)
            version = subprocess.check_output([program, "--version"], text=True).strip()
            expected = configuration["build_tools"].get(
                tool + "_binary_version", configuration["build_tools"][tool]
            )
            if version != expected:
                raise ValueError(f"Use the pinned {tool} build tool")
        environment["NINJA"] = programs["ninja"]
        environment["PKG_CONFIG"] = programs["pkgconf"]
        parsers = extract(
            fetch(configuration["build_tools"]["win_flex_bison"], cache), work / "parsers", None
        )
        # Dependency discovery must use our static, reviewed builds.
        (dependencies / "lib/pkgconfig").mkdir(exist_ok=True)
        (dependencies / "lib/pkgconfig/zlib.pc").write_text(
            f"prefix={dependencies.as_posix()}\nlibdir=${{prefix}}/lib\nincludedir=${{prefix}}/include\n"
            "Name: zlib\nDescription: Pinned static zlib\nVersion: 1.3.2\nLibs: -L${libdir} -lzlib\nCflags: -I${includedir}\n"
        )
        # OpenSSL's Windows install exports CMake files but no pkg-config
        # files. Without an explicit descriptor Meson can silently select the
        # runner's unrelated shared OpenSSL from Program Files.
        prefix = f"prefix={dependencies.as_posix()}\nlibdir=${{prefix}}/lib\nincludedir=${{prefix}}/include\n"
        version = configuration["openssl"]["version"]
        for name, extra in {
            "libcrypto": "Libs: -L${libdir} -llibcrypto\nLibs.private: -lws2_32 -lgdi32 -ladvapi32 -lcrypt32 -luser32\n",
            "libssl": "Libs: -L${libdir} -llibssl\nRequires.private: libcrypto\n",
            "openssl": "Requires: libssl libcrypto\n",
        }.items():
            (dependencies / "lib/pkgconfig" / (name + ".pc")).write_text(
                prefix
                + f"Name: {name}\nDescription: Pinned static OpenSSL\nVersion: {version}\n"
                + "Cflags: -I${includedir}\n"
                + extra
            )
        environment["PKG_CONFIG_PATH"] = str(dependencies / "lib/pkgconfig")
        environment["PKG_CONFIG_LIBDIR"] = environment["PKG_CONFIG_PATH"]
        environment["PKGCONF_PYPI_EMBEDDED_ONLY"] = "1"
        environment["PATH"] = str(dependencies / "bin") + os.pathsep + environment.get("PATH", "")
        found_ssl = subprocess.check_output(
            [programs["pkgconf"], "--modversion", "openssl"], env=environment, text=True
        ).strip()
        if found_ssl != version:
            raise ValueError("The compiler did not discover the pinned OpenSSL build")
        environment["INCLUDE"] = (
            str(dependencies / "include") + os.pathsep + environment.get("INCLUDE", "")
        )
        environment["LIB"] = str(dependencies / "lib") + os.pathsep + environment.get("LIB", "")
        disabled = [
            "bonjour",
            "bsd_auth",
            "docs",
            "docs_pdf",
            "gssapi",
            "icu",
            "ldap",
            "libcurl",
            "libnuma",
            "liburing",
            "libxml",
            "libxslt",
            "llvm",
            "lz4",
            "nls",
            "pam",
            "plperl",
            "plpython",
            "pltcl",
            "readline",
            "selinux",
            "systemd",
            "tap_tests",
            "zstd",
        ]
        run(
            [
                programs["meson"],
                "setup",
                work / "pg-build",
                sources["postgresql"],
                "--prefix=" + str(install),
                "--buildtype=release",
                "--wrap-mode=nodownload",
                "-Db_vscrt=mt",
                "-Dssl=openssl",
                "-Dzlib=enabled",
                "-Dextra_include_dirs=" + str(dependencies / "include"),
                "-Dextra_lib_dirs=" + str(dependencies / "lib"),
                "-DBISON=" + str(parsers / "win_bison.exe"),
                "-DFLEX=" + str(parsers / "win_flex.exe"),
                *["-D" + name + "=disabled" for name in disabled],
            ]
        )
        run([programs["meson"], "compile", "-C", work / "pg-build", "-j", "2"])
        run([programs["meson"], "install", "-C", work / "pg-build"])
        run(
            [
                "nmake",
                "/f",
                "Makefile.win",
                "PGROOT=" + str(install),
                "PG_CFLAGS=/MT /O2 /fp:fast",
                "CC=cl",
                "install",
            ],
            sources["pgvector"],
        )
    else:
        environment["CPPFLAGS"] = "-I" + str(dependencies / "include")
        environment["LDFLAGS"] = "-L" + str(dependencies / "lib")
        if operating_system == "macos":
            environment["LDFLAGS"] += " -Wl,-headerpad_max_install_names"
        run(
            [
                "sh",
                "./configure",
                "--prefix=" + str(install),
                "--with-ssl=openssl",
                "--with-zlib",
                "--without-icu",
                "--without-readline",
                "--without-ldap",
                "--without-gssapi",
                "--without-libcurl",
                "--without-liburing",
                "--without-libnuma",
                "--without-lz4",
                "--without-zstd",
                "--without-libxml",
                "--without-libxslt",
                "--without-llvm",
                "--without-perl",
                "--without-python",
                "--without-tcl",
            ],
            sources["postgresql"],
        )
        relocation = (
            ["rpath=-Wl,-rpath,'$$ORIGIN/../lib:$$ORIGIN/..:$$ORIGIN'"]
            if operating_system == "linux"
            else []
        )
        run(["make", "-j2", *relocation], sources["postgresql"])
        run(["make", "install", *relocation], sources["postgresql"])
        run(
            [
                "make",
                "-j2",
                "PG_CONFIG=" + str(install / "bin/pg_config"),
                "OPTFLAGS=",
                *relocation,
            ],
            sources["pgvector"],
        )
        run(
            [
                "make",
                "install",
                "PG_CONFIG=" + str(install / "bin/pg_config"),
                "OPTFLAGS=",
                *relocation,
            ],
            sources["pgvector"],
        )

    (install / "tools").mkdir()
    openssl = "openssl.exe" if operating_system == "windows" else "openssl"
    shutil.copy2(dependencies / "bin" / openssl, install / "tools" / openssl)
    # Development headers/static libraries are only required while building
    # pgvector. The installed runtime retains extension SQL and time-zone data.
    shutil.rmtree(install / "include", ignore_errors=True)
    for path in sorted(install.rglob("*")):
        if path.is_file() and path.suffix in (".a", ".lib", ".pdb", ".pc"):
            path.unlink()
    for path in list(install.rglob("*")):
        if path.is_symlink():
            target = path.resolve(strict=True)
            if not target.is_relative_to(install) or not target.is_file():
                raise ValueError("Unexpected native runtime symlink")
            value = target.read_bytes()
            mode = target.stat().st_mode & 0o777
            path.unlink()
            path.write_bytes(value)
            path.chmod(mode)
    if operating_system == "macos":
        relocate_macos(install)
    return package_runtime(install, output, sources, configuration, operating_system, architecture)


def package_runtime(
    install: Path,
    output: Path,
    sources: dict[str, Path],
    configuration: dict,
    operating_system: str,
    architecture: str,
) -> Path:
    """Inspect and inventory the finished tree before creating a new archive."""
    libraries = inspect(install, operating_system)
    licenses = install / "licenses"
    licenses.mkdir()
    for name in COMPONENTS:
        shutil.copy2(sources[name] / configuration[name]["license"], licenses / (name + ".txt"))
    metadata = {
        "format": 1,
        "component": "postgresql",
        "platform": operating_system,
        "architecture": architecture,
        "sources": {name: configuration[name] for name in COMPONENTS},
        "cpu": "baseline; pgvector OPTFLAGS cleared",
        "source_adjustments": (
            ["libpq permits static OpenSSL's pthread_exit, retaining process-exit rejection"]
            if operating_system != "windows"
            else ["Meson selects static OpenSSL and its private system dependencies"]
        )
        + (
            ["libpq permits Apple's _atexit cleanup registration"]
            if operating_system == "macos"
            else []
        ),
        "static_libraries": ["OpenSSL", "zlib"],
        "dependencies": libraries,
        "files": {
            path.relative_to(install).as_posix(): {
                "sha256": digest(path),
                "size": path.stat().st_size,
                "executable": bool(path.stat().st_mode & 0o111),
            }
            for path in sorted(install.rglob("*"))
            if path.is_file()
        },
    }
    (install / "mnemion-runtime.json").write_text(json.dumps(metadata, indent=2) + "\n")
    output.mkdir(parents=True, exist_ok=True)
    archive_path = (
        output
        / f"mnemion-postgres-{configuration['postgresql']['version']}-{operating_system}-{architecture}.zip"
    )
    with zipfile.ZipFile(
        archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for path in sorted(install.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(install).as_posix())
    print(
        json.dumps(
            {
                "archive": str(archive_path),
                "sha256": digest(archive_path),
                "bytes": archive_path.stat().st_size,
            }
        )
    )
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    build(args.output.resolve(), args.cache.resolve(), args.work.resolve())


if __name__ == "__main__":
    main()
