"""The explicit CLI owns preparation; nested startup and model helpers do not."""

import json
from types import SimpleNamespace

import pytest

from mnemion import maintenance_measurement
from mnemion.product_telemetry import aggregate, policy
from mnemion.service import cli, librarian_provider, model_registry


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "private"
    monkeypatch.setattr(policy, "default_directory", lambda: root)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "absent-company.json")
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/telemetry")
    policy.configure(root, {"enabled": True, "expected_revision": 0, "disclosure_version": 1})
    return root


def registry_fixture(monkeypatch, kind, effect):
    calls = []

    def prepare():
        calls.append("prepare")
        effect()

    model = SimpleNamespace(
        prepare=prepare,
        tokenizer=SimpleNamespace(prepare=prepare),
        generation=SimpleNamespace(id="PRIVATE_GENERATION", dimensions=384),
        profile=SimpleNamespace(describe=lambda: {"id": "PRIVATE_PROFILE"}),
    )

    def selected(name):
        assert name == "PRIVATE_PROFILE"
        return model

    registry = SimpleNamespace(
        profile=selected,
        get=selected,
        providers={"PRIVATE_PROFILE": model},
        close=lambda: calls.append("close"),
    )
    target = (
        model_registry.ModelRegistry
        if kind == "embedding"
        else librarian_provider.LibrarianRegistry
    )
    monkeypatch.setattr(target, "from_environment", lambda: registry)
    arguments = (
        ["prepare-model", "--profile"] if kind == "embedding" else ["librarian-models", "--prepare"]
    )
    return [*arguments, "PRIVATE_PROFILE"], calls


@pytest.mark.parametrize("kind", ["embedding", "librarian_tokenizer"])
def test_explicit_preparation_records_one_confirmed_outcome_without_model_identity(
    installation, monkeypatch, capsys, kind
):
    arguments, calls = registry_fixture(monkeypatch, kind, lambda: None)
    assert cli.main(arguments) == 0
    assert calls == ["prepare", "close"]
    assert "PRIVATE" in capsys.readouterr().out
    rows = aggregate.preview(installation)
    assert {row["workflow"] for row in rows} == {"models.prepare"}
    assert {row["surface"] for row in rows} == {"headless"}
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert next(row for row in rows if row["metric"] == "outcomes")["bucket"] == "success"
    assert "PRIVATE" not in json.dumps(rows) and "384" not in json.dumps(rows)
    assert b"PRIVATE" not in (installation / policy.DATABASE_NAME).read_bytes()


@pytest.mark.parametrize("kind", ["embedding", "librarian_tokenizer"])
@pytest.mark.parametrize("condition", ["nested", "unavailable", "late_opt_out", "observer_failure"])
def test_preparation_preserves_work_without_inheriting_or_resurrecting_consent(
    installation, monkeypatch, capsys, kind, condition
):
    def effect():
        if condition == "late_opt_out":
            policy.configure(installation, {"enabled": False, "expected_revision": 0})

    arguments, calls = registry_fixture(monkeypatch, kind, effect)
    if condition == "unavailable":
        monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", False)
    if condition == "observer_failure":
        monkeypatch.setattr(
            maintenance_measurement.workflow,
            "begin",
            lambda *_a, **_k: (_ for _ in ()).throw(OSError("PRIVATE_OBSERVER")),
        )
    assert cli.main(arguments, preparation_owner=condition != "nested") == 0
    assert calls == ["prepare", "close"]
    assert "PRIVATE" in capsys.readouterr().out
    assert aggregate.preview(installation) == []


@pytest.mark.parametrize("kind", ["embedding", "librarian_tokenizer"])
def test_failed_preparation_keeps_registry_cleanup_and_never_replays(
    installation, monkeypatch, kind
):
    def effect():
        raise OSError("PRIVATE_PROVIDER_ERROR")

    arguments, calls = registry_fixture(monkeypatch, kind, effect)
    with pytest.raises(OSError if kind == "embedding" else RuntimeError):
        cli.main(arguments)
    assert calls == ["prepare", "close"]
    rows = aggregate.preview(installation)
    assert next(row for row in rows if row["metric"] == "outcomes")["bucket"] == "unconfirmed"
    assert "PRIVATE" not in json.dumps(rows)


def test_librarian_model_listing_does_not_acquire_a_preparation_owner(
    installation, monkeypatch, capsys
):
    _, calls = registry_fixture(monkeypatch, "librarian_tokenizer", lambda: None)
    assert cli.main(["librarian-models"]) == 0
    assert calls == ["close"]
    assert "PRIVATE_PROFILE" in capsys.readouterr().out
    assert aggregate.preview(installation) == []


def test_interrupted_preparation_preserves_the_interrupt_and_registry_cleanup(
    installation, monkeypatch
):
    def effect():
        raise KeyboardInterrupt

    arguments, calls = registry_fixture(monkeypatch, "embedding", effect)
    with pytest.raises(KeyboardInterrupt):
        cli.main(arguments)
    assert calls == ["prepare", "close"]
    rows = aggregate.preview(installation)
    assert next(row for row in rows if row["metric"] == "outcomes")["bucket"] == "cancelled"
