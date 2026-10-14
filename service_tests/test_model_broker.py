"""Real pinned loopback TLS shares one model and rejects port impersonation."""

import ssl

import httpx
import pytest

from mnemion import local_state
from mnemion.service.embeddings import EmbeddedChunk, Generation, LocalEmbedder
from mnemion.service.errors import ServiceError
from mnemion.service.inference_limits import InferenceGate
from mnemion.service.model_broker import ModelBroker, SharedLocalEmbedder
from mnemion.service.model_registry import ModelRegistry

GENERATION = Generation("shared-protocol-fixture", 4, {"runtime": "fastembed"})


class CountingLocal(LocalEmbedder):
    def __init__(self, cache):
        super().__init__(cache, generation=GENERATION, offline=True)
        self.loads, self.queries = 0, []

    def _prepare(self):
        if self._model is None:
            self.loads += 1
            self._model = object()

    def _query(self, text):
        self._prepare()
        self.queries.append(text)
        return [1.0, 0.0, 0.0, 0.0]

    def _document(self, text):
        self._prepare()
        return [EmbeddedChunk(0, len(text), [0.5, 0.5, 0.5, 0.5])]

    def token_count(self, text):
        with self._inference_gate.acquire():
            self._prepare()
            return len(text.split())


def owner(tmp_path):
    model = CountingLocal(tmp_path / "cache")
    return model, ModelRegistry(model)


def proxy(directory, tmp_path):
    return SharedLocalEmbedder(
        directory, tmp_path / "unused-cache", generation=GENERATION, offline=True
    )


def test_search_indexing_and_counting_share_one_loaded_model_and_preserve_unicode_spans(tmp_path):
    model, registry = owner(tmp_path)
    directory = tmp_path / "broker"
    client = proxy(directory, tmp_path)
    with ModelBroker(registry, directory):
        client.prepare()
        assert client.query("question") == model.query("direct")
        text = "Électricité et mémoire 🪐"
        assert client.document(text) == model.document(text)
        large = "é🪐\n" * 170000
        assert client.document(large) == model.document(large)
        assert client.token_count(text) == 4
        assert model.loads == 1 and client._model is None
        observation = client.worker_status()
        assert observation["available"] and observation["scope"] == "indexing_worker"
        assert observation["model_cache"]["loaded_local_models"] == 1
        assert model.loads == 1
        assert not list(directory.rglob("key.pem")) and not list(directory.glob(".identity-*"))
    client.close()


def test_another_tls_listener_cannot_receive_text_using_a_stale_or_reused_port(tmp_path):
    original, registry = owner(tmp_path)
    other, other_registry = owner(tmp_path)
    first, second = tmp_path / "first", tmp_path / "second"
    with ModelBroker(registry, first), ModelBroker(other_registry, second):
        expected = local_state.read(first / "address.json")
        impostor = local_state.read(second / "address.json")
        local_state.write(
            first / "address.json", {**impostor, "certificate": expected["certificate"]}
        )
        client = proxy(first, tmp_path)
        with pytest.raises(ServiceError) as error:
            client.query("must never reach the other listener")
        assert error.value.code == "embedding_unavailable"
        assert not original.queries and not other.queries
        assert original.loads == other.loads == 0
        client.close()


def test_worker_restart_rotates_credential_and_pin_and_client_recovers_without_loading(tmp_path):
    model, registry = owner(tmp_path)
    directory = tmp_path / "broker"
    client = proxy(directory, tmp_path)
    with ModelBroker(registry, directory):
        assert client.query("before")
        first = local_state.read(directory / "address.json")
    with pytest.raises(ServiceError, match="unavailable"):
        client.query("during restart")
    with ModelBroker(registry, directory):
        second = local_state.read(directory / "address.json")
        assert first["token"] != second["token"] and first["certificate"] != second["certificate"]
        assert client.query("after")
    assert client._model is None and model.loads == 1
    client.close()


def test_authentication_profile_and_queue_limits_do_not_start_extra_inference(tmp_path):
    model, registry = owner(tmp_path)
    model._inference_gate = registry.inference_gate = InferenceGate(max_queued=0, wait_seconds=0.01)
    directory = tmp_path / "broker"
    with ModelBroker(registry, directory):
        address = local_state.read(directory / "address.json")
        with httpx.Client(
            verify=ssl.create_default_context(cadata=address["certificate"]), trust_env=False
        ) as connection:
            url = f"https://127.0.0.1:{address['port']}/embedding"
            request = {"operation": "query", "generation": GENERATION.id, "text": "synthetic"}
            assert connection.post(url, json=request).status_code == 401
            headers = {"Authorization": "Bearer " + address["token"]}
            assert (
                connection.post(
                    url, headers=headers, json={**request, "generation": "f" * 64}
                ).status_code
                == 503
            )
            assert (
                connection.post(
                    url, headers=headers, json={**request, "extra": "forbidden"}
                ).status_code
                == 422
            )
        client = proxy(directory, tmp_path)
        with model._inference_gate.acquire(), pytest.raises(ServiceError) as error:
            client.query("busy")
        assert error.value.code == "inference_busy" and model.loads == 0
        client.close()


def test_missing_worker_never_falls_back_to_loading_another_local_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMION_MODEL_BROKER", str(tmp_path / "missing"))
    api = ModelRegistry.from_environment()
    worker = ModelRegistry.from_environment(shared_models=False)
    assert isinstance(api.default, SharedLocalEmbedder)
    assert not isinstance(worker.default, SharedLocalEmbedder)
    with pytest.raises(ServiceError) as error:
        api.default.query("worker is down")
    assert error.value.code == "embedding_unavailable" and api.default._model is None


def test_current_cli_enables_sharing_for_an_old_supervisors_existing_role_contract(
    tmp_path, monkeypatch
):
    from mnemion.service.model_broker import configure_managed_sharing

    monkeypatch.setenv("MNEMION_SUPERVISED_STATE", str(tmp_path))
    monkeypatch.setenv("MNEMION_SUPERVISED_ROLE", "api")
    monkeypatch.delenv("MNEMION_MODEL_BROKER", raising=False)
    configure_managed_sharing("serve")
    assert isinstance(ModelRegistry.from_environment().default, SharedLocalEmbedder)
    monkeypatch.setenv("MNEMION_MODEL_SHARING", "0")
    configure_managed_sharing("serve")
    assert not isinstance(ModelRegistry.from_environment().default, SharedLocalEmbedder)
