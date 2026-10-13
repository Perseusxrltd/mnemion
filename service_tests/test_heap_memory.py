"""Unsupported allocators must retain portable cleanup without native calls."""

from types import SimpleNamespace

import pytest

from mnemion.service import heap_memory


@pytest.fixture(autouse=True)
def reset_allocator_cache():
    resolve = heap_memory._glibc_trim
    resolve.cache_clear()
    yield
    resolve.cache_clear()


@pytest.mark.parametrize("platform", ["win32", "darwin", "freebsd13"])
def test_other_platforms_do_not_load_or_call_a_glibc_allocator(monkeypatch, platform):
    def forbidden(_):
        pytest.fail("A glibc allocator must not be resolved on another operating system")

    monkeypatch.setattr(heap_memory, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(heap_memory, "ctypes", SimpleNamespace(CDLL=forbidden))
    assert heap_memory.release_unused_heap() is None


@pytest.mark.parametrize("kind", ["musl", "missing_trim", "loader_unavailable"])
def test_missing_native_support_is_a_cached_optional_hint(monkeypatch, kind):
    calls = []

    def load(path):
        assert path is None, "Cleanup must not load an external allocator library"
        calls.append(path)
        if kind == "loader_unavailable":
            raise OSError("synthetic native loader detail")
        if kind == "musl":
            return SimpleNamespace(malloc_trim=lambda _: pytest.fail("Non-glibc allocator"))
        return SimpleNamespace(gnu_get_libc_version=object())

    monkeypatch.setattr(heap_memory, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(heap_memory, "ctypes", SimpleNamespace(CDLL=load))
    assert heap_memory.release_unused_heap() is None
    assert heap_memory.release_unused_heap() is None
    assert calls == [None]


def test_an_unavailable_allocator_hint_does_not_raise_native_details(monkeypatch):
    def unavailable(_):
        raise OSError("synthetic native allocator detail")

    monkeypatch.setattr(heap_memory, "_glibc_trim", lambda: unavailable)
    assert heap_memory.release_unused_heap() is None
