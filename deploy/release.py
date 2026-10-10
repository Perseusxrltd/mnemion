"""Validate immutable release versions and complete architecture-specific feeds."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("A stable version is required")
    from mnemion.version import __version__

    if version != __version__:
        raise ValueError("Python versions disagree")
    for name in ("packages/client", "studio/frontend", "studio/electron"):
        for filename in ("package.json", "package-lock.json"):
            if json.loads((root / name / filename).read_text())["version"] != version:
                raise ValueError(f"Version mismatch: {name}/{filename}")
    files = list(args.artifacts.iterdir())
    for architecture in ("x64", "arm64"):
        for suffix in ("", "-mac", "-linux" if architecture == "x64" else "-linux-arm64"):
            feed = args.artifacts / f"latest-{architecture}{suffix}.yml"
            if not feed.is_file():
                raise ValueError(f"Missing update feed: {feed.name}")
            text = feed.read_text()
            if not re.search(rf"^version: ['\"]?{re.escape(version)}['\"]?\s*$", text, re.M):
                raise ValueError(f"Wrong version in {feed.name}")
            # All generated feed URLs must point at artifacts in this release.
            urls = re.findall(r"^\s*-?\s*url:\s*['\"]?([^'\"\s]+)", text, re.M)
            if not urls or any(
                Path(url).name != url or not (args.artifacts / url).is_file() for url in urls
            ):
                raise ValueError(f"Missing or external update payload in {feed.name}")
    checksums = []
    for path in sorted(files):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Release assets must be regular files")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        checksums.append(f"{digest.hexdigest()}  {path.name}")
    (args.artifacts / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n")
    print(f"Validated Mnemion {version}: {len(files)} assets and six update feeds")


if __name__ == "__main__":
    main()
