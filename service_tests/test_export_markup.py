"""Untrusted Markdown stays readable without becoming executable vault markup."""

from html.parser import HTMLParser
from uuid import UUID

import yaml

from mnemion.service.export import ExportService
from mnemion.service.markdown import literal, note
from mnemion.service.models import ExportInput, MemoryInput, RevisionInput
from service_tests.test_exports import unzip


class PlainCode(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.text = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_data(self, data):
        self.text.append(data)


def test_markup_and_template_openers_remain_literal():
    text = '<%* fixture(); %>\n```dataviewjs\nfixture();\n```\n<img src="https://example.invalid/beacon">\n</code></pre>\na < b & c'
    rendered = literal(text)
    parser = PlainCode()
    parser.feed(rendered)
    assert parser.tags == [("pre", []), ("code", [])]
    assert "".join(parser.text) == text
    assert "<%" not in rendered
    metadata = {"aliases": [text], "uri": "https://example.invalid/<%fixture%>", "version": 2}
    rendered = note(metadata, "Safe body")
    assert "<%" not in rendered
    assert yaml.safe_load(rendered.split("---\n")[1]) == metadata


def test_export_neutralizes_current_history_sources_and_titles(env):
    content = '<%* fixture(); %>\n<img src="https://example.invalid/beacon">'
    saved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content=content,
            subject="<% subject %>",
            metadata={"title": "![external](https://example.invalid/beacon)"},
            source={"title": "<% source %>", "content": content},
        ),
        "markup",
    )
    env.memory.revise(
        env.owner,
        UUID(saved["memory_id"]),
        RevisionInput(content=content + "\nUpdated", expected_version=1, reason="Fixture update"),
        "markup-update",
    )
    files = unzip(ExportService(env.db).export(env.owner, ExportInput(space_ids=[env.space])))
    markdown = [body for name, body in files.items() if name.endswith(".md")]
    assert markdown
    assert all("<%" not in body and "<img " not in body for body in markdown)
    assert any("&lt;img " in body for body in markdown)
    assert any("#^evidence" in body for body in markdown)
