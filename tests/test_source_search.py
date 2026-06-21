from mnemion.sources.store import SourceStore


def test_source_search_uses_fts_and_privacy_filter(tmp_path):
    public_file = tmp_path / "public.md"
    private_file = tmp_path / "private.md"
    public_file.write_text("Hybrid retrieval uses reciprocal rank fusion.")
    private_file.write_text("Sensitive payroll token evidence should stay private.")
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    public = store.add_path(public_file, privacy_class="public")
    private = store.add_path(private_file, privacy_class="sensitive")

    public_hits = store.search("reciprocal rank", privacy_class="public")
    sensitive_hits = store.search("payroll token", privacy_class="sensitive")
    default_hits = store.search("payroll token")

    assert public_hits and public_hits[0]["source_id"] == public["source_id"]
    assert sensitive_hits and sensitive_hits[0]["source_id"] == private["source_id"]
    assert default_hits and default_hits[0]["source_id"] == private["source_id"]


def test_source_list_filters_type_and_limit(tmp_path):
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")
    for i in range(3):
        path = tmp_path / f"note_{i}.txt"
        path.write_text(f"note {i} source vault")
        store.add_path(path, source_type="text")

    rows = store.list_sources(source_type="text", limit=2)

    assert len(rows) == 2
    assert all(row["source_type"] == "text" for row in rows)
