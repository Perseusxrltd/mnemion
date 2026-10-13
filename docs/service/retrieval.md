# Search passages and source evidence

Search returns bounded passages so people and agents can inspect a result
without downloading every full memory. The matched-passage correction is in
development for [issue 35](https://github.com/Perseusxrltd/mnemion/issues/35);
check [release status](../RELEASE_STATUS.md) before assuming a published server
includes it.

`POST /v1/recall` and MCP `memory_search` use the same retrieval service. Each
hit has two independently meaningful spans:

- `text` and `memory_span` identify a passage in the memory revision.
- `evidence.excerpt`, `evidence.start` and `evidence.end` identify a passage in
  the cited source revision. A summary and its original source can differ.

Offsets count Unicode code points from zero; the start is inclusive and the
end exclusive. A source slice between those offsets reproduces the excerpt
exactly. The source revision identifier and hash continue to identify the
complete original source. Do not interpret a source offset as a byte offset or
JavaScript UTF-16 index.

The correction selects up to 4,000 characters around the strongest local
coverage of query words. Repeated words have bounded weight. When no query word
matches, an available embedding span supplies the memory passage. When an
embedding chunk is shorter than 4,000 characters, its size also bounds the
memory passage so context consumption does not expand. A derived memory's
source is searched separately, within its original cited range; memory
offsets are never copied into a different source. The selector scans text without
loading another model and retains only one display window of matches.

`text_truncated` and `evidence.excerpt_truncated` indicate that a result shows
only part of its memory or cited source. Fetching the memory still returns the
complete revision and original evidence. Context packs preserve the selected
memory passage and source citation after checking access and revision freshness
again. Obsidian export continues to use complete recorded evidence.

A well-positioned excerpt does not establish that the result answers a question
or is current. This correction does not change document ranking, introduce a
relevance threshold, resolve contradictions or supply a recency signal. Those
retrieval requirements remain in the [roadmap](../PRODUCT_REQUIREMENTS.md).

For scope, supply nonempty `space_ids`, or use `all_accessible: true` with an
empty list. Both resolve current permissions. Source removal, quarantine,
withdrawal and authorization checks also apply to passages.
