import yaml

from mnemion.wiki.renderer import merge_generated_page, render_page, slugify_wikilink


def test_render_page_outputs_yaml_frontmatter_and_generated_markers():
    page = render_page(
        page_id="wiki_abc",
        page_type="concept",
        title="Hybrid Retrieval",
        body="Hybrid retrieval combines lexical and semantic search.",
        generated_sections={"summary": "A source-backed summary."},
        source_hashes=["sha256:abc"],
        claim_ids=["claim_abc"],
    )

    frontmatter = yaml.safe_load(page.split("---", 2)[1])
    assert frontmatter["mnemion_page_id"] == "wiki_abc"
    assert frontmatter["page_type"] == "concept"
    assert "<!-- MNEMION:BEGIN generated section=summary -->" in page
    assert "<!-- MNEMION:END -->" in page


def test_merge_generated_page_preserves_manual_sections():
    existing = """---
title: Old
---
# Hybrid Retrieval

<!-- MNEMION:BEGIN generated section=summary -->
old generated
<!-- MNEMION:END -->

## Manual Notes

Keep this note.
"""
    generated = render_page(
        page_id="wiki_new",
        page_type="concept",
        title="Hybrid Retrieval",
        generated_sections={"summary": "new generated"},
    )

    merged = merge_generated_page(existing, generated)

    assert "new generated" in merged
    assert "old generated" not in merged
    assert "## Manual Notes" in merged
    assert "Keep this note." in merged


def test_slugify_wikilink_is_obsidian_and_windows_safe():
    assert slugify_wikilink("Hybrid Retrieval!") == "hybrid-retrieval"
