"""Real local/broker scheduling with deterministic native-call fixtures."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import threading
import time

import pytest

from mnemion.service.embeddings import LocalEmbedder
from mnemion.service.errors import ServiceError
from mnemion.service.inference_limits import InferenceGate
from mnemion.service.local_tokenizer import SharedModelTokenizer
from mnemion.service.memory_budget import GIB, MIB, MemoryBudget, MemoryOptions, MemorySample
from mnemion.service.model_broker import ModelBroker, SharedLocalEmbedder
from mnemion.service.model_registry import ModelRegistry


class Vector:
    def tolist(self):
        return [1.0] + [0.0] * 383


class NativeFixture:
    def __init__(self, *, coordinated=True):
        self.coordinated = coordinated
        self.first_started = threading.Event()
        self.release_first = threading.Event()
        self.release_rest = threading.Event()
        self.active = self.peak = 0
        self.batches = []

    def embed(self, texts, batch_size=None):
        texts = list(texts)
        query = texts[0].startswith("query: ")
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if not query:
                self.batches.append(len(texts))
                if self.coordinated:
                    if len(self.batches) == 1:
                        self.first_started.set()
                        assert self.release_first.wait(5)
                    else:
                        assert self.release_rest.wait(5)
            yield from (Vector() for _ in texts)
        finally:
            self.active -= 1


class LocalFixture(LocalEmbedder):
    def __init__(self, path, backend):
        super().__init__(path, offline=True)
        self.backend, self.loads = backend, 0

    def _prepare(self):
        if self._memory_budget:
            self._memory_budget.admit(self)
        if self._model is not None:
            return
        from tokenizers import Tokenizer
        from tokenizers.models import WordLevel
        from tokenizers.pre_tokenizers import Whitespace

        tokenizer = Tokenizer(WordLevel({"[UNK]": 0, "x": 1}, unk_token="[UNK]"))
        tokenizer.pre_tokenizer = Whitespace()
        tokenizer.enable_truncation(max_length=512)
        tokenizer.enable_padding(length=512, pad_id=0, pad_token="[UNK]")
        self._tokenizer = SharedModelTokenizer(tokenizer)
        self._model = self.backend
        self.loads += 1


TEXT = " ".join(["x"] * ((512 - 1) * 336 + 384))
# Captured from the original full-document implementation and independent
# source inventory: 512 unchanged Unicode spans and deterministic fixture vectors.
ORIGINAL_OUTPUT = "5adc8f2db1831d93ca2a7a32b7f60fa0e3617a675ac7342357759db4abe13dbd"


def verify_chunks(chunks):
    assert len(chunks) == 512
    assert (
        hashlib.sha256(
            json.dumps([(c.start, c.end, c.vector) for c in chunks]).encode()
        ).hexdigest()
        == ORIGINAL_OUTPUT
    )


def wait_queued(gate):
    deadline = time.monotonic() + 3
    while gate.snapshot()["queued"] < 1 and time.monotonic() < deadline:
        time.sleep(0.001)
    assert gate.snapshot()["queued"] >= 1


@pytest.mark.parametrize("through_broker", [False, True])
def test_waiting_query_completes_between_batches_without_changing_evidence(
    tmp_path, through_broker
):
    native = NativeFixture()
    model = LocalFixture(tmp_path / "unused-cache", native)
    registry = ModelRegistry(model, idle_seconds=0)
    model._inference_gate = registry.inference_gate = InferenceGate(wait_seconds=1)
    client = SharedLocalEmbedder(
        tmp_path / "broker", tmp_path / "unused-client-cache", offline=True
    )
    with ModelBroker(registry, tmp_path / "broker"), ThreadPoolExecutor(max_workers=2) as pool:
        document = pool.submit(model.document, TEXT)
        try:
            assert native.first_started.wait(3)
            query = pool.submit(client.query if through_broker else model.query, "x")
            wait_queued(registry.inference_gate)
            native.release_first.set()
            assert query.result(timeout=3) == Vector().tolist()
            # Indexing is held at its second batch until the caller observes
            # the query result. Holding the old document-wide gate fails here.
            assert not document.done()
        finally:
            native.release_first.set()
            native.release_rest.set()
        verify_chunks(document.result(timeout=5))
        assert native.peak == 1
        assert model.generation.id == client.generation.id
        assert client._model is None and model.loads == 1
        assert registry.inference_gate.snapshot()["completed"] == 2
        assert registry.inference_gate.snapshot()["rejected"] == 0
    client.close()
    registry.close()


@pytest.mark.parametrize("pressure", [False, True])
def test_resume_rechecks_released_model_and_changed_memory_budget(tmp_path, pressure):
    native = NativeFixture()
    model = LocalFixture(tmp_path, native)
    gate = model._inference_gate = InferenceGate(wait_seconds=1)
    budget = model._memory_budget = MemoryBudget(
        sample=lambda: MemorySample(16 * GIB, 12 * GIB, 256 * MIB)
    )

    def other_profile():
        with gate.acquire():
            assert native.active == 0
            # Models can be evicted while another profile owns execution.
            model._unload()
            if pressure:
                budget.configure(MemoryOptions(mode="manual", limit_mib=256), "changed")

    with ThreadPoolExecutor(max_workers=2) as pool:
        document = pool.submit(model.document, TEXT)
        try:
            assert native.first_started.wait(3)
            foreground = pool.submit(other_profile)
            wait_queued(gate)
            native.release_first.set()
            foreground.result(timeout=3)
        finally:
            native.release_first.set()
            native.release_rest.set()
        if pressure:
            with pytest.raises(ServiceError) as failure:
                document.result(timeout=5)
            assert failure.value.code == "inference_memory_budget"
            assert model.loads == 1
        else:
            verify_chunks(document.result(timeout=5))
            assert model.loads == 2
    assert native.peak == 1
    assert gate.snapshot()["active"] == gate.snapshot()["queued"] == 0


def test_adaptive_slices_retain_the_ram_batch_limit_and_complete_inventory(tmp_path):
    native = NativeFixture(coordinated=False)
    model = LocalFixture(tmp_path, native)
    # A loaded model has enough headroom, with the real RAM policy limiting
    # batches to four. No physical memory allocation or model download occurs.
    model._prepare()
    model._memory_budget = MemoryBudget(
        MemoryOptions(mode="manual", limit_mib=2048),
        sample=lambda: MemorySample(16 * GIB, 8 * GIB, 1800 * MIB),
    )
    verify_chunks(model.document(TEXT))
    assert native.batches[0] == 1 and max(native.batches) == 4
    assert sum(native.batches) == 512 and native.peak == 1
