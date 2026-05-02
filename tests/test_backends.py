import pytest

from mnemion.backends.base import GetResult, QueryResult, UnsupportedFilterError
from mnemion.backends.chroma import DEFAULT_HNSW_METADATA, validate_where
from mnemion.backends.registry import available_backends, get_backend


def test_typed_results_remain_dict_compatible():
    query = QueryResult(ids=[["a"]], documents=[["doc"]], metadatas=[[{"wing": "x"}]])
    get = GetResult(ids=["a"], documents=["doc"], metadatas=[{"wing": "x"}])

    assert query["ids"] == [["a"]]
    assert query.ids == [["a"]]
    assert get["documents"] == ["doc"]
    assert get.documents == ["doc"]


def test_chroma_filter_validation_rejects_unsupported_operator():
    with pytest.raises(UnsupportedFilterError):
        validate_where({"source_file": {"$contains": "secret"}})


def test_chroma_backend_creates_guarded_collection(anaktoron_path):
    backend = get_backend("chroma", anaktoron_path=anaktoron_path)
    collection = backend.get_collection("mnemion_drawers", create=True)

    metadata = collection.raw_collection.metadata
    for key, value in DEFAULT_HNSW_METADATA.items():
        assert metadata[key] == value
    assert "chroma" in available_backends()


def test_backend_public_names_use_anaktoron_with_palace_aliases():
    from mnemion.backends.base import (
        AnaktoronNotFoundError,
        AnaktoronRef,
        PalaceNotFoundError,
        PalaceRef,
    )
    from mnemion.backends.registry import resolve_backend_for_anaktoron, resolve_backend_for_palace

    assert PalaceNotFoundError is AnaktoronNotFoundError
    assert PalaceRef is AnaktoronRef
    assert resolve_backend_for_palace is resolve_backend_for_anaktoron
