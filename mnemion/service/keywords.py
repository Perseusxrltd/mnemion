"""Scoped key-term support for prose queries with no complete lexical match."""

import re

KEYWORD_WEIGHT = 0.5
_WORDS = re.compile(r"\w+", re.UNICODE)


def permits_keyword_fallback(query: str) -> bool:
    # Explicit web-search syntax retains its existing meaning. Short keyword
    # queries and unusually long prompts stay on the ordinary search channels.
    if '"' in query or re.search(r"(?<!\S)-(?=\S)|\bor\b", query, re.IGNORECASE):
        return False
    return 3 <= len(_WORDS.findall(query)) <= 32


# English/French stop words come from PostgreSQL's bundled dictionaries. We
# retain original simple lexemes rather than stemming only the query against an
# unstemmed index. Term frequencies cover only the already-authorized inventory.
# A term counts once per memory; repeating prose cannot inflate its support.
KEYWORD_CANDIDATES = """
, query_terms AS MATERIALIZED (
    SELECT word,plainto_tsquery('simple',word) AS query
    FROM unnest(tsvector_to_array(to_tsvector('simple',%(query)s))) AS words(word)
    WHERE length(word) BETWEEN 2 AND 128
      AND cardinality(ts_lexize('english_stem',word))>0
      AND cardinality(ts_lexize('french_stem',word))>0
), query_size AS (
    SELECT count(*) AS count FROM query_terms
), keyword_matches AS MATERIALIZED (
    SELECT e.memory_id,e.space_id,e.revision_id,e.source_group,e.rank_time,e.rank_path,t.word,
           char_length(r.content) AS characters,
           to_tsvector('simple',coalesce(r.subject,'')) @@ t.query AS in_label
    FROM eligible e JOIN mnemion.memory_revisions r
      ON r.tenant_id=mnemion.tenant() AND r.space_id=e.space_id AND r.id=e.revision_id
    CROSS JOIN query_terms t
    WHERE (SELECT count FROM query_size) BETWEEN 2 AND 24
      AND r.search_text @@ t.query
), frequencies AS (
    SELECT word,count(*) AS count FROM keyword_matches GROUP BY word
), corpus_size AS (
    SELECT count(*) AS count FROM eligible
), keyword_scores AS (
SELECT k.memory_id,k.space_id,k.revision_id,k.source_group,k.rank_time,k.rank_path,
       array_agg(k.word ORDER BY k.word) AS keyword_terms,
       count(*) AS keyword_matches,
       (SELECT count FROM query_size) AS keyword_requested,
       sum(ln(1.0+(SELECT count FROM corpus_size)/f.count::numeric)
           * CASE WHEN k.in_label THEN 1.5 ELSE 1 END)
           / (1+0.1*ln(1.0+k.characters/1000.0)) AS keyword_score
FROM keyword_matches k JOIN frequencies f ON f.word=k.word
GROUP BY k.memory_id,k.space_id,k.revision_id,k.source_group,k.rank_time,k.rank_path,k.characters
), keyword_sources AS (
    SELECT *,row_number() OVER (PARTITION BY source_group
        ORDER BY keyword_score DESC,memory_id) AS source_position FROM keyword_scores
)
SELECT * FROM keyword_sources
ORDER BY source_position,keyword_score DESC,memory_id LIMIT %(limit)s
"""
