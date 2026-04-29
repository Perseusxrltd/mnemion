from mnemion.sources import (
    AdapterSchema,
    AnaktoronContext,
    BaseSourceAdapter,
    DrawerRecord,
    FieldSpec,
    RouteHint,
    SchemaConformanceError,
    SourceRef,
    validate_drawer_record,
)
from mnemion.sources.registry import discover_adapters


class DummyAdapter(BaseSourceAdapter):
    name = "dummy"
    adapter_version = "1.0"

    def ingest(self, *, source, anaktoron):
        yield DrawerRecord(
            content="hello",
            source_file=source.local_path or "dummy",
            metadata={"kind": "note", "count": 1},
            route_hint=RouteHint(wing="test", room="general"),
        )

    def describe_schema(self):
        return AdapterSchema(
            version="1.0",
            fields={
                "kind": FieldSpec(type="string", required=True, description="Kind"),
                "count": FieldSpec(type="int", required=False, description="Count"),
            },
        )


def test_source_ref_keeps_options_non_secret():
    ref = SourceRef(local_path=".", options={"mode": "scan"})
    assert ref.options == {"mode": "scan"}


def test_dummy_adapter_conforms():
    adapter = DummyAdapter()
    context = AnaktoronContext(anaktoron_path="/tmp/anaktoron", collection_name="mnemion_drawers")
    records = list(adapter.ingest(source=SourceRef(local_path="x"), anaktoron=context))

    assert records[0].content == "hello"
    validate_drawer_record(records[0], adapter.describe_schema())


def test_validate_drawer_record_rejects_nested_metadata():
    record = DrawerRecord(content="x", source_file="x", metadata={"nested": {"no": "dicts"}})
    schema = AdapterSchema(version="1", fields={})

    try:
        validate_drawer_record(record, schema)
    except SchemaConformanceError as exc:
        assert "flat scalar" in str(exc)
    else:
        raise AssertionError("nested metadata should fail")


def test_discover_adapters_handles_no_entry_points(monkeypatch):
    class EmptyEntryPoints:
        def select(self, group):
            return []

    monkeypatch.setattr("mnemion.sources.registry.entry_points", lambda: EmptyEntryPoints())

    assert discover_adapters() == {}
