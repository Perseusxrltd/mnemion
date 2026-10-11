"""Collect release licenses and a CycloneDX inventory without network access.

For desktop builds, select Python distributions from the actual PyInstaller
analysis plus its bootloader. For server images, inventory the locked runtime
environment. Frontend production dependencies are conservatively included even
when the bundler removes unused exports. Build-only npm tools are excluded.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata as metadata
import json
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from urllib.parse import quote

LICENSE_NAME = re.compile(
    r"^(licen[sc]es?|copying|copyright|notices?|third[._ -]?party[._ -]?(?:licen[sc]es?|notices?))([._-]|$)",
    re.I,
)


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings(item)


def python_components(analysis: Path | None):
    distributions = list(metadata.distributions())
    if analysis is None:
        return distributions
    if analysis.stat().st_size > 64 * 1024**2:
        raise ValueError("Unexpectedly large PyInstaller analysis")
    paths = {
        Path(value).resolve()
        for value in strings(ast.literal_eval(analysis.read_text(encoding="utf-8")))
        if Path(value).is_absolute() and Path(value).is_file()
    }
    selected, matched = [], set()
    for distribution in distributions:
        files = {
            Path(distribution.locate_file(item)).resolve() for item in distribution.files or ()
        }
        intersection = paths & files
        if intersection or canonical(distribution.metadata["Name"]) == "pyinstaller":
            selected.append(distribution)
            matched.update(intersection)
    unknown = [p for p in paths - matched if {"site-packages", "dist-packages"} & set(p.parts)]
    if unknown:
        raise ValueError(
            "A bundled third-party Python file has no distribution record; review the build"
        )
    return selected


def copy_licenses(output: Path, identity: str, files: list[Path]) -> list[dict]:
    if not files:
        raise ValueError(f"No license text found for {identity}; inspect this release input")
    directory = output / "third-party" / hashlib.sha256(identity.encode()).hexdigest()[:16]
    directory.mkdir(parents=True, exist_ok=True)
    records, seen = [], set()
    for source in files:
        if source.stat().st_size > 4 * 1024**2:
            raise ValueError(f"License file is unexpectedly large for {identity}")
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        target = directory / (digest[:16] + ".txt")
        target.write_bytes(content)
        records.append({"file": target.relative_to(output).as_posix(), "sha256": digest})
    return records


def native_python_licenses(root: Path, analysis: Path | None) -> list[Path]:
    # Standalone Python distributions can embed native libraries in libpython,
    # where PyInstaller cannot inventory them as separate extension files.
    # Match the actual binary, rather than assuming a CPython version identifies
    # its OpenSSL, compression, terminal, or other bundled dependencies.
    # Standard Windows CPython builds zlib into python3xx.dll. Include the
    # matching upstream notice; this alone is not a standalone Unix runtime.
    probes = {"_ssl", "_hashlib"} if sys.platform == "win32" else {"_ssl", "_hashlib", "zlib"}
    if analysis is None:
        return []
    if not (probes & set(sys.builtin_module_names)):
        if sys.platform == "win32" and "zlib" in sys.builtin_module_names:
            import zlib

            directory = root / "deploy" / "license-overrides"
            catalog = json.loads((directory / "native-zlib.json").read_text(encoding="utf-8"))
            record = catalog.get(zlib.ZLIB_RUNTIME_VERSION)
            if not record or Path(record["file"]).name != record["file"]:
                raise ValueError("Review the bundled Windows zlib notice for this runtime version")
            path = directory / record["file"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("Native zlib notice checksum mismatch")
            return [path]
        return []
    library = sysconfig.get_config_var("LDLIBRARY")
    if not library:
        raise ValueError("Cannot identify the statically bundled Python runtime")
    path = Path(sys.base_prefix) / "lib" / library
    if not path.is_file():
        raise ValueError("Cannot locate the statically bundled Python runtime")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    directory = root / "deploy" / "license-overrides"
    catalog = json.loads((directory / "native-python.json").read_text(encoding="utf-8"))
    record = catalog.get(digest)
    if (
        not record
        or record["python_version"] != sys.version.split()[0]
        or record["platform"] != sys.platform
    ):
        raise ValueError(
            "Unreviewed statically bundled Python: use standard CPython or add its verified native notices"
        )
    files = []
    for item in record["files"]:
        if Path(item["file"]).name != item["file"]:
            raise ValueError("Invalid native Python notice path")
        source = directory / item["file"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Native Python notice checksum mismatch")
        files.append(source)
    return files


def collect_python(output: Path, analysis: Path | None, root: Path) -> list[dict]:
    components = []
    overrides_dir = root / "deploy" / "license-overrides"
    overrides = json.loads((overrides_dir / "manifest.json").read_text(encoding="utf-8"))
    for distribution in python_components(analysis):
        name, version = distribution.metadata["Name"], distribution.version
        if canonical(name) == "mnemion":
            continue
        files = [
            Path(distribution.locate_file(item))
            for item in distribution.files or ()
            if LICENSE_NAME.match(item.name) and Path(distribution.locate_file(item)).is_file()
        ]
        purl = f"pkg:pypi/{canonical(name)}@{version}"
        override = overrides.get(purl, {})
        if not files:
            for item in override.get("files", []):
                if Path(item["file"]).name != item["file"]:
                    raise ValueError("Invalid license override path")
                source = overrides_dir / item["file"]
                if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError("License override checksum mismatch")
                files.append(source)
        license_name = distribution.metadata.get("License-Expression") or distribution.metadata.get(
            "License", override.get("license_label", "See license files")
        )
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": purl,
                "license_label": license_name.splitlines()[0][:250],
                "license_files": copy_licenses(output, purl, files),
            }
        )
    candidates = [
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE",
        Path(sysconfig.get_path("stdlib")) / "LICENSE.txt",
        Path(f"/usr/share/doc/python{sys.version_info.major}.{sys.version_info.minor}/copyright"),
    ]
    components.append(
        {
            "type": "framework",
            "name": "CPython",
            "version": sys.version.split()[0],
            "purl": f"pkg:generic/cpython@{sys.version.split()[0]}",
            "license_label": "Python Software Foundation and bundled notices",
            "license_files": copy_licenses(
                output,
                "CPython",
                [p for p in candidates if p.is_file()] + native_python_licenses(root, analysis),
            ),
        }
    )
    return components


def collect_frontend(output: Path, frontend: Path) -> list[dict]:
    # Use Node with npm's JS entry point on Windows; do not invoke a .cmd shell
    # with interpolated package names or license text.
    import os

    npm_entry = os.environ.get("npm_execpath")
    if npm_entry:
        command = [shutil.which("node") or "node", npm_entry]
    else:
        npm = shutil.which("npm")
        if not npm or sys.platform == "win32":
            raise ValueError("Run notice collection through npm on Windows")
        command = [npm]
    result = subprocess.run(
        [*command, "--prefix", str(frontend), "ls", "--all", "--omit=dev", "--parseable"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    components, seen = [], set()
    for value in result.stdout.splitlines():
        directory = Path(value)
        manifest = directory / "package.json"
        if not manifest.is_file():
            raise ValueError("npm reported an incomplete production dependency")
        package = json.loads(manifest.read_text(encoding="utf-8"))
        name, version = package["name"], package["version"]
        if directory.resolve() == frontend.resolve() or name == "@mnemion/client":
            continue
        purl = f"pkg:npm/{quote(name, safe='/')}@{quote(version, safe='')}"
        if purl in seen:
            continue
        seen.add(purl)
        files = [p for p in directory.iterdir() if p.is_file() and LICENSE_NAME.match(p.name)]
        if not files:
            overrides_dir = Path(__file__).resolve().parent / "license-overrides"
            overrides = json.loads((overrides_dir / "manifest.json").read_text(encoding="utf-8"))
            for item in overrides.get(purl, {}).get("files", []):
                if Path(item["file"]).name != item["file"]:
                    raise ValueError("Invalid npm notice override path")
                source = overrides_dir / item["file"]
                if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError("npm notice checksum mismatch")
                files.append(source)
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": purl,
                "license_label": str(package.get("license", "See license files")),
                "license_files": copy_licenses(output, purl, files),
            }
        )
    return components


def collect_fonts(output: Path, frontend: Path) -> list[dict]:
    """Inventory the exact locally bundled typefaces and their redistribution licenses."""
    root = frontend / "public/fonts"
    manifest = json.loads((root / "provenance.json").read_text())
    components = []
    for family in ("inter", "outfit"):
        records = [item for item in manifest["fonts"] if item["file"].startswith(family + "-")]
        if len(records) != 2:
            raise ValueError(f"The {family} font requires both reviewed local subsets")
        for record in records:
            name = record["file"]
            if name not in {family + "-latin.woff2", family + "-latin-ext.woff2"}:
                raise ValueError("Unrecognized bundled font subset")
            data = (frontend / "src/assets/fonts" / name).read_bytes()
            if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("Bundled font differs from its reviewed provenance")
        version = re.search(r"/v(\d+)/", records[0]["source"]).group(1)
        identity = f"pkg:generic/google-fonts/{family}@{version}"
        components.append(
            {
                "type": "file",
                "name": family.title(),
                "version": version,
                "purl": identity,
                "license_label": "SIL Open Font License 1.1",
                "license_files": copy_licenses(output, identity, [root / (family + "-OFL.txt")]),
            }
        )
    return components


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--analysis", type=Path)
    parser.add_argument("--frontend", type=Path)
    parser.add_argument("--electron", type=Path)
    parser.add_argument("--sparkle", type=Path, help="Verified native Sparkle distribution")
    parser.add_argument("--python", action="store_true", help="Include Python runtime components")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "NOTICE"):
        shutil.copyfile(args.root / name, args.output / name)
    components = collect_python(args.output, args.analysis, args.root) if args.python else []
    if args.frontend:
        components.extend(collect_frontend(args.output, args.frontend))
        components.extend(collect_fonts(args.output, args.frontend))
    if args.electron:
        components.extend(collect_frontend(args.output, args.electron))
    if args.sparkle:
        config = json.loads((args.root / "studio/electron/native/sparkle.json").read_text())
        identity = f"pkg:github/sparkle-project/Sparkle@{config['version']}"
        components.append(
            {
                "type": "framework",
                "name": "Sparkle",
                "version": config["version"],
                "purl": identity,
                "license_label": "MIT and bundled third-party license notices",
                "license_files": copy_licenses(args.output, identity, [args.sparkle / "LICENSE"]),
            }
        )
    components = list({item["purl"]: item for item in components}.values())
    components.sort(key=lambda item: item["purl"])
    (args.output / "inventory.json").write_text(
        json.dumps(
            {
                "format": "mnemion-release-licenses-v1",
                "scope": "PyInstaller-selected Python components and bootloader"
                if args.analysis
                else "Installed runtime components",
                "frontend_scope": "Complete npm production dependency tree; unused exports may be removed by bundling",
                "components": components,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    bom = {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "components": []}
    for component in components:
        bom["components"].append(
            {
                **{key: component[key] for key in ("type", "name", "version", "purl")},
                "bom-ref": component["purl"],
                "licenses": [{"license": {"name": component["license_label"]}}],
                "properties": [
                    {"name": "mnemion:license-file", "value": item["file"]}
                    for item in component["license_files"]
                ],
            }
        )
    (args.output / "sbom.cdx.json").write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"license_components": len(components), "output": str(args.output)}))


if __name__ == "__main__":
    main()
