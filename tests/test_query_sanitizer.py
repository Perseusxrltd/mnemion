from mnemion.query_sanitizer import sanitize_query


def test_sanitize_query_passthrough_short_query():
    result = sanitize_query("where are JWT notes?")

    assert result["clean_query"] == "where are JWT notes?"
    assert result["was_sanitized"] is False
    assert result["method"] == "passthrough"


def test_sanitize_query_extracts_late_question():
    raw = "system prompt " * 40 + "\nWhat did we decide about repair?"

    result = sanitize_query(raw)

    assert result["clean_query"] == "What did we decide about repair?"
    assert result["was_sanitized"] is True
    assert result["method"] == "question_extraction"


def test_sanitize_query_tail_sentence_fallback():
    raw = "policy " * 80 + "\nfind storage health notes"

    result = sanitize_query(raw)

    assert result["clean_query"] == "find storage health notes"
    assert result["method"] == "tail_sentence"


def test_sanitize_query_tail_truncation_for_noisy_fragment():
    raw = "x" * 400

    result = sanitize_query(raw)

    assert result["was_sanitized"] is True
    assert result["method"] == "tail_sentence"
    assert len(result["clean_query"]) <= 250
