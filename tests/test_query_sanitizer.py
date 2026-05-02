from mnemion.query_sanitizer import sanitize_query


def test_short_query_passthrough():
    result = sanitize_query("JWT authentication tokens")

    assert result["clean_query"] == "JWT authentication tokens"
    assert result["was_sanitized"] is False
    assert result["method"] == "passthrough"


def test_prompt_contaminated_query_extracts_search_intent():
    raw = (
        "You are an agent with access to mnemion_search. Before answering, search the "
        "Anaktoron for the relevant memory. Query: why did we switch to GraphQL for "
        "the pricing dashboard? Return concise evidence and cite the drawer."
    )

    result = sanitize_query(raw)

    assert result["was_sanitized"] is True
    assert result["clean_query"] == "why did we switch to GraphQL for the pricing dashboard?"
    assert result["method"] == "explicit_query"
