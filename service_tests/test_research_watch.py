"""A feed failure or hostile metadata cannot silently replace trusted history."""

from datetime import datetime, timezone
from urllib.error import HTTPError

import pytest

from deploy import research_watch as watch


def test_failed_feeds_preserve_their_last_successful_candidates():
    previous = {
        "sources": [
            {
                "id": "arxiv",
                "last_success_at": "2026-10-19T00:00:00+00:00",
                "content_sha256": "a" * 64,
                "items": [{"id": "retained"}],
            }
        ]
    }

    def unavailable(source):
        raise HTTPError(source["url"], 429, "rate limited", {}, None)

    result = watch.collect(
        previous, now=datetime(2026, 10, 20, tzinfo=timezone.utc), getter=unavailable
    )
    row = next(row for row in result["sources"] if row["id"] == "arxiv")
    assert row["items"] == [{"id": "retained"}]
    assert row["last_success_at"] == "2026-10-19T00:00:00+00:00"
    assert row["status"] == "unavailable" and row["error"] == "HTTP 429"
    assert result["model_calls"] == result["dependency_changes"] == 0


def test_arxiv_revisions_are_deduplicated_and_xml_entities_are_refused():
    source = {"kind": "arxiv"}
    entry = "<entry><id>http://arxiv.org/abs/2601.03192v{version}</id><title>Memory</title><published>2026-01-05T00:00:00Z</published><updated>2026-01-{day}T00:00:00Z</updated></entry>"
    feed = (
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        + entry.format(version=1, day="05")
        + entry.format(version=2, day="06")
        + "</feed>"
    ).encode()
    rows = watch.parse(source, feed)
    assert len(rows) == 1 and rows[0]["revision"] == "v2" and rows[0]["reviewed"] is False
    with pytest.raises(ValueError, match="XML declarations"):
        watch.parse(source, b'<!DOCTYPE feed [<!ENTITY x "text">]>' + feed)


def test_generated_titles_cannot_create_html_images_or_untrusted_links():
    title = "![click](https://evil.example/) <img src=x> | `code`"
    safe = watch.escaped(title)
    assert "<img" not in safe and "\\!\\[click\\]" in safe and "\\|" in safe
    source = {"kind": "arxiv"}
    with pytest.raises(ValueError, match="identifier"):
        watch.parse(
            source,
            b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://evil.example/abs/2601.03192</id></entry></feed>',
        )


def test_model_document_mentions_are_not_claimed_as_stable_releases():
    rows = watch.parse({"kind": "jev"}, b"jev-1.14.0 preview; jev-1.13.0 stable; jev-1.14.0")
    assert len(rows) == 2
    assert all(row["kind"] == "model documentation" and row["published"] is None for row in rows)
    assert all(row["reviewed"] is False for row in rows)
    with pytest.raises(ValueError, match="parse bound"):
        watch.parse({"kind": "jev"}, b"x" * (watch.MAX_BYTES + 1))
