import pytest

from mnemion.sources.extractors import SourceExtractionError, extract_text
from mnemion.sources.ingest import ingest_source
from mnemion.sources.store import SourceStore


def test_ingest_markdown_creates_chunks_with_offsets(tmp_path):
    source_file = tmp_path / "paper.md"
    source_file.write_text("# Paper\n\n" + "Hybrid retrieval reduces vector blur. " * 80)
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")

    result = ingest_source(store, source_file, title="Paper", privacy_class="private")
    read = store.read_source(result["source_id"], include_chunks=True)

    assert result["status"] == "created"
    assert read["source"]["title"] == "Paper"
    assert read["chunks"]
    assert read["chunks"][0]["start_offset"] == 0
    assert read["chunks"][0]["end_offset"] > 0


def test_jsonl_extractor_flattens_records(tmp_path):
    source_file = tmp_path / "events.jsonl"
    source_file.write_text('{"role":"user","content":"alpha"}\nnot-json\n{"content":"beta"}\n')

    extracted = extract_text(source_file)

    assert "alpha" in extracted.text
    assert "beta" in extracted.text
    assert extracted.source_type == "jsonl"


def test_pdf_extractor_is_clear_optional_stub(tmp_path):
    source_file = tmp_path / "paper.pdf"
    source_file.write_bytes(b"%PDF-1.7")

    with pytest.raises(SourceExtractionError, match="PDF"):
        extract_text(source_file)


def test_missing_source_file_error_is_clean(tmp_path):
    store = SourceStore(db_path=tmp_path / "kg.sqlite3", source_path=tmp_path / "sources")

    with pytest.raises(FileNotFoundError):
        ingest_source(store, tmp_path / "missing.md")
