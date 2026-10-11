"""Host installation archives must fail before executing altered or unsafe files."""

import hashlib
import io
import json
import tarfile
import zipfile

import pytest

from deploy.build_native_postgres import extract, fetch
from deploy.probe_native_postgres import expand


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "source/../../escape", "source/C:escape"]
)
def test_source_traversal_is_rejected(tmp_path, name):
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as out:
        entry = tarfile.TarInfo(name)
        entry.size = 3
        out.addfile(entry, io.BytesIO(b"bad"))
    with pytest.raises(ValueError, match="Unsafe"):
        extract(archive, tmp_path / "expanded", "source")
    assert not (tmp_path / "escape").exists()


def test_source_links_and_case_collisions_are_rejected(tmp_path):
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as out:
        entry = tarfile.TarInfo("source/link")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "../outside"
        out.addfile(entry)
    with pytest.raises(ValueError, match="Unsafe"):
        extract(archive, tmp_path / "linked", "source")
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("File", b"one")
        out.writestr("file", b"two")
    with pytest.raises(ValueError, match="Unsafe"):
        extract(archive, tmp_path / "colliding", None)


def test_cached_source_hash_is_checked_without_replacing_it(tmp_path):
    expected = hashlib.sha256(b"reviewed source").hexdigest()
    cached = tmp_path / expected
    cached.write_bytes(b"altered source")
    with pytest.raises(ValueError, match="pinned digest"):
        fetch(
            {"sha256": expected, "url": "https://ftp.postgresql.org/pub/source/fixture.tar.gz"},
            tmp_path,
        )
    assert cached.read_bytes() == b"altered source"


def test_inventory_detects_changed_native_code_and_unlisted_files(tmp_path):
    original = b"native binary fixture"
    metadata = {
        "format": 1,
        "component": "postgresql",
        "files": {
            "bin/postgres": {
                "sha256": hashlib.sha256(original).hexdigest(),
                "size": len(original),
                "executable": False,
            }
        },
    }

    def bundle(name, content, extra=False):
        archive = tmp_path / (name + ".zip")
        with zipfile.ZipFile(archive, "w") as out:
            out.writestr("mnemion-runtime.json", json.dumps(metadata))
            out.writestr("bin/postgres", content)
            if extra:
                out.writestr("unexpected-library", b"extra")
        return archive

    assert expand(bundle("valid", original), tmp_path / "valid")["component"] == "postgresql"
    with pytest.raises(ValueError, match="differs"):
        expand(bundle("altered", original.replace(b"native", b"unsafe")), tmp_path / "altered")
    with pytest.raises(ValueError, match="inventory"):
        expand(bundle("extra", original, True), tmp_path / "extra")
