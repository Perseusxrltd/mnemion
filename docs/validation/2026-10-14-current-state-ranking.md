# Current-state ranking — 14 October 2026

Source change for 4.3.1, responding to the reopened
[issue 31](https://github.com/Perseusxrltd/mnemion/issues/31).
Publication and platform acceptance are recorded in
[release status](../RELEASE_STATUS.md).

## Focused behavior checks

Forty-one checks passed across current-ranking, search controls, literal retrieval,
query-only MCP access, MCP compatibility and the generated operation catalog. PostgreSQL cases use real scoped
transactions, source revisions and non-owner service roles. The fixture embedder
tests policy and transport behavior; it is not a retrieval-quality benchmark.

- A newer relevant answer outranks a stronger older lexical match, while an
  unrelated new document remains outside lexical candidates.
- The strong identifier/filename channel no longer forces archived task reports
  above current answers. Pure relevance restores the prior priority; newest-first
  sorting keeps its separate behavior.
- Original relevance thresholds retain archived evidence. Historical requests
  use their requested reference time; future source dates gain no extra weight.
- Archive matching respects literal directory boundaries, custom names, Windows
  separators and Unicode normalization. Invalid/unbounded controls are rejected.
- Existing private-space, source-lease, quarantine, explicit-exclusion,
  correction-race and compact-discovery checks passed with the new ordering.
- MCP passes explicit policy and preserves query-only scope behavior. Python
  search/context calls omit the new field unless explicitly requested, preserving
  compatibility with older servers.

Client and Studio production builds and lint passed. A Chromium session against
a disposable HTTPS service and real PostgreSQL exercised personal login, search,
default current-answer ordering, restoring pure relevance, actual submitted
policy values, invalid-input blocking and visible ranking factors. Desktop
(1280 × 960) and mobile (390 × 844) views were inspected; there was no horizontal
page overflow or browser exception. This used synthetic memory and the fixture
model, with no production data or cloud calls.

## Read-only live sample and offline replay

Three read-only requests to the existing 4.2.5 shared workspace verified the
independent administrator and captured the two public issue queries, at limit 30.
No memory or credential was changed. Only rank metadata was retained privately;
no memory text, private paths, private memory IDs or credentials enter the repository.

The [sanitized replay](2026-10-14-current-ranking-replay.json) applies the new
default ordering to those captured candidates:

| Reported evidence | Previous position | New position in the captured sample |
| --- | --- | --- |
| Current T-0053 report | 6 | 1 |
| T-0057 `DONE.md` | 4 | 2 |
| T-0057 `HANDOFF.md` | 5 | 3 |

Archived results went from two to zero in the top five for each sampled query.
This is an offline reranking of an existing result pool, not a claim that the
new service has already run on the shared host. The request limit and corpus
time differ from the reporter's earlier five-hit sample. Two observed queries
do not establish general quality, truth or current-state correctness.

No embedding call, re-index, database migration or candidate-window expansion
is introduced by this policy. Broader held-out quality evaluation, dated-section
chunking and automatic contradiction resolution remain open requirements.
