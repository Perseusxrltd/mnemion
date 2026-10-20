"""Publish bounded, validated website text from the canonical Git documentation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile

from jsonschema import Draft202012Validator

SOURCE = "docs/website/content.json"
SCHEMA = "docs/website/content.schema.json"
OUTPUT = "deploy/website-content.json"
MAX_BYTES = 64 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate website content key")
        result[key] = value
    return result


def read_json(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Website content must be a bounded regular JSON file")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def version(value: str) -> tuple[int, ...]:
    if not re.fullmatch(
        r"(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})", value
    ):
        raise ValueError("A stable content version is required")
    return tuple(map(int, value.split(".")))


def build(root: Path) -> dict:
    content, schema = read_json(root / SOURCE), read_json(root / SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(content)
    if version(content["minimum_release"]) < (4, 0, 0):
        raise ValueError("Website content must describe the current product generation")

    def check_links(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"doc", "updatesDoc"}:
                    path = root / item
                    if (
                        path.is_symlink()
                        or not path.is_file()
                        or not path.resolve().is_relative_to(root.resolve())
                    ):
                        raise ValueError("Website guide is missing or leaves the repository")
                check_links(item)
        elif isinstance(value, list):
            for item in value:
                check_links(item)
        elif isinstance(value, str) and value != value.strip():
            raise ValueError("Website text must not contain surrounding whitespace")

    check_links(content)
    compact = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    payload = {
        "schema_version": 1,
        "source_path": SOURCE,
        "content_sha256": hashlib.sha256(compact.encode("utf-8")).hexdigest(),
        "content": content,
    }
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Website content exceeds its publication limit")
    return payload


def publish(root: Path, *, write: bool = False) -> dict:
    payload = build(root)
    published = read_json(root / "deploy/published-release.json")
    if published.get("draft") is not False or published.get("prerelease") is not False:
        raise ValueError("Website text requires published stable release metadata")
    tag = published.get("tag_name", "")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise ValueError("Published release tag is missing")
    minimum = payload["content"]["minimum_release"]
    held = version(minimum) > version(tag[1:])
    target = root / OUTPUT
    if target.is_symlink():
        raise ValueError("The website manifest must not be a symbolic link")
    changed = not held and (not target.exists() or read_json(target) != payload)
    if write and changed:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        try:
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return {
        "valid": True,
        "changed": changed,
        "written": bool(write and changed),
        "held_for_release": held,
        "minimum_release": minimum,
        "content_sha256": payload["content_sha256"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(publish(Path(__file__).resolve().parents[1], write=args.write)))


if __name__ == "__main__":
    main()
