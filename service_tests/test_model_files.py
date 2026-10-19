"""Pinned cache reuse must work without Hub API access or repeated downloads."""

import huggingface_hub as hub
from huggingface_hub.errors import LocalEntryNotFoundError
import pytest

from mnemion.service.model_files import pinned_model_directory


CONFIG = {
    "repository": "fixture/pinned-model",
    "revision": "a" * 40,
    "model_file": "onnx/model_quantized.onnx",
}
FILES = (
    "onnx/model_quantized.onnx",
    "tokenizer.json",
    "tokenizer_config.json",
    "config.json",
    "special_tokens_map.json",
)


def cached(tmp_path, names=FILES):
    root = tmp_path / "snapshots" / CONFIG["revision"]
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    return root


def test_complete_snapshot_never_contacts_hub_even_in_online_mode(tmp_path, monkeypatch):
    root = cached(tmp_path)
    monkeypatch.setattr(
        hub, "try_to_load_from_cache", lambda filename, **kwargs: str(root / filename)
    )

    def unexpected(**kwargs):
        raise AssertionError("A cached model must not contact the Hub")

    monkeypatch.setattr(hub, "hf_hub_download", unexpected)
    monkeypatch.setattr(hub, "snapshot_download", unexpected)
    assert pinned_model_directory(CONFIG, tmp_path) == root
    assert pinned_model_directory(CONFIG, tmp_path, offline=True) == root


def test_partial_cache_downloads_only_the_missing_pinned_file(tmp_path, monkeypatch):
    root = cached(tmp_path, FILES[1:])

    def lookup(filename, **kwargs):
        path = root / filename
        return str(path) if path.is_file() else None

    calls = []

    def download(filename, **kwargs):
        calls.append((filename, kwargs))
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"downloaded")
        return str(path)

    monkeypatch.setattr(hub, "try_to_load_from_cache", lookup)
    monkeypatch.setattr(hub, "hf_hub_download", download)
    assert pinned_model_directory(CONFIG, tmp_path) == root
    assert calls == [
        (
            FILES[0],
            {
                **{k: CONFIG[k] for k in ("revision",)},
                "repo_id": CONFIG["repository"],
                "cache_dir": str(tmp_path),
                "token": False,
            },
        )
    ]
    assert pinned_model_directory(CONFIG, tmp_path) == root
    assert len(calls) == 1


def test_offline_missing_file_fails_without_any_download(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "try_to_load_from_cache", lambda **kwargs: None)

    def unexpected(**kwargs):
        raise AssertionError("Offline loading cannot download a file")

    monkeypatch.setattr(hub, "hf_hub_download", unexpected)
    with pytest.raises(LocalEntryNotFoundError):
        pinned_model_directory(CONFIG, tmp_path, offline=True)


def test_known_absent_optional_files_keep_runtime_defaults(tmp_path, monkeypatch):
    root = cached(tmp_path, FILES[:3])
    monkeypatch.setattr(
        hub,
        "try_to_load_from_cache",
        lambda filename, **kwargs: (
            str(root / filename) if filename in FILES[:3] else hub._CACHED_NO_EXIST
        ),
    )
    assert pinned_model_directory(CONFIG, tmp_path) == root


def test_mixed_snapshot_files_are_rejected(tmp_path, monkeypatch):
    first, second = cached(tmp_path / "one"), cached(tmp_path / "two")
    monkeypatch.setattr(
        hub,
        "try_to_load_from_cache",
        lambda filename, **kwargs: str((first if filename == FILES[0] else second) / filename),
    )
    with pytest.raises(RuntimeError, match="same snapshot"):
        pinned_model_directory(CONFIG, tmp_path)


@pytest.mark.parametrize("name", ["../model.onnx", "/model.onnx", "onnx\\model.onnx", "."])
def test_model_filename_cannot_escape_the_snapshot(tmp_path, name):
    with pytest.raises(ValueError):
        pinned_model_directory({**CONFIG, "model_file": name}, tmp_path)


def test_corrupt_cached_model_never_reaches_inference(tmp_path, monkeypatch):
    import fastembed
    from mnemion.service import model_files
    from mnemion.service.embeddings import LocalEmbedder

    root = cached(tmp_path)
    monkeypatch.setattr(model_files, "pinned_model_directory", lambda *args, **kwargs: root)

    def unexpected(*args, **kwargs):
        raise AssertionError("Unverified model bytes must not reach the inference runtime")

    monkeypatch.setattr(fastembed, "TextEmbedding", unexpected)
    with pytest.raises(RuntimeError, match="checksum failed"):
        LocalEmbedder(tmp_path).prepare()
