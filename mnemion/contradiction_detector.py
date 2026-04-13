#!/usr/bin/env python3
"""
contradiction_detector.py — Two-Stage Conflict Detection for Mnemion
=======================================================================

Stage 1 — Quick LLM judge (single prompt, no Anaktoron context)
  • Compares new drawer text against top-k similar existing drawers
  • LLM outputs: conflict_type, confidence, winner, reason
  • If confidence ≥ STAGE1_THRESHOLD → auto-resolve
  • Otherwise → Stage 2

Stage 2 — Deep resolve with Anaktoron context
  • Pulls additional Anaktoron context for both drawers (semantic search)
  • Second LLM pass with enriched context
  • Resolves based on that + records outcome

LLM backend is configured via: mnemion llm setup
Supports: ollama, lmstudio, vllm, custom, none (disabled)

All detection runs in daemon threads — saves never block.
Fetch speed is unaffected: trust status is pre-computed at save time.
"""

import json
import logging
import threading
import time
from typing import Optional, List, Dict, Any

logger = logging.getLogger("mnemion.contradiction")

# ── Configuration ─────────────────────────────────────────────────────────────
STAGE1_THRESHOLD = 0.80  # auto-resolve if LLM confidence ≥ this
CANDIDATES_K = 2  # candidates to check per new drawer
MAX_TOKENS_S1 = 512
MAX_TOKENS_S2 = 768

# ── Rate limiting (keeps background LLM pressure anecdotal) ──────────────────
INTER_REQUEST_SLEEP = 5.0  # seconds between each LLM call within a thread
GLOBAL_COOLDOWN_SEC = 120  # minimum seconds between any two detection runs

_last_detection_time: float = 0.0
_rate_lock = threading.Lock()

# ── Prompt templates ──────────────────────────────────────────────────────────

STAGE1_SYSTEM = """You are a memory consistency checker. Your job is to detect conflicts between memory fragments.

Conflict types:
- direct_contradiction: Statements that cannot both be true (e.g., "likes coffee" vs "hates coffee")
- temporal_update: Newer fact supersedes older one (e.g., old address vs new address)
- partial_overlap: Overlapping content, one is more specific or accurate
- none: No meaningful conflict

Respond ONLY with valid JSON, no markdown, no explanation:
{"conflict_type": "<type>", "confidence": <0.0-1.0>, "winner": "<a|b|none>", "reason": "<one sentence>"}

winner="a" means memory_a is more accurate/current.
winner="b" means memory_b is more accurate/current.
winner="none" means no conflict or ambiguous."""

STAGE1_USER = """Compare these two memories:

MEMORY_A (existing, id={id_a}):
{text_a}

MEMORY_B (new):
{text_b}

Is there a conflict? Respond with JSON only."""

STAGE2_SYSTEM = """You are a memory consistency resolver with access to additional context.
A potential conflict between two memories is ambiguous. Use the provided context to determine which memory is more accurate.

Respond ONLY with valid JSON, no markdown:
{"conflict_type": "<type>", "confidence": <0.0-1.0>, "winner": "<a|b|none>", "reason": "<one sentence>", "resolution_note": "<brief explanation using context>"}"""

STAGE2_USER = """Two memories may conflict. Additional Anaktoron context is provided to help you decide.

MEMORY_A (existing, id={id_a}):
{text_a}

MEMORY_B (new):
{text_b}

RELATED CONTEXT FROM ANAKTORON:
{context}

Which memory is more accurate? Respond with JSON only."""


# ── LLM helpers ───────────────────────────────────────────────────────────────


def _get_backend():
    """Lazy-load the configured LLM backend."""
    from .llm_backend import get_backend

    return get_backend()


def _parse_llm_json(raw: Optional[str]) -> Optional[Dict]:
    if not raw:
        return None
    try:
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM JSON: {raw[:200]}")
        return None


def stage1_check(new_text: str, candidate: Dict[str, Any]) -> Optional[Dict]:
    """Single-pair Stage 1 conflict check."""
    backend = _get_backend()
    messages = [
        {"role": "system", "content": STAGE1_SYSTEM},
        {
            "role": "user",
            "content": STAGE1_USER.format(
                id_a=candidate["id"],
                text_a=candidate["text"][:1200],
                text_b=new_text[:1200],
            ),
        },
    ]
    raw = backend.chat(messages, MAX_TOKENS_S1)
    result = _parse_llm_json(raw)
    if result:
        result["candidate_id"] = candidate["id"]
    return result


def stage2_resolve(
    new_text: str, candidate: Dict[str, Any], context_snippets: List[str]
) -> Optional[Dict]:
    """Stage 2 deep resolve with enriched Anaktoron context."""
    backend = _get_backend()
    context = (
        "\n---\n".join(context_snippets[:5])
        if context_snippets
        else "(no additional context found)"
    )
    messages = [
        {"role": "system", "content": STAGE2_SYSTEM},
        {
            "role": "user",
            "content": STAGE2_USER.format(
                id_a=candidate["id"],
                text_a=candidate["text"][:1200],
                text_b=new_text[:1200],
                context=context[:2000],
            ),
        },
    ]
    raw = backend.chat(messages, MAX_TOKENS_S2)
    result = _parse_llm_json(raw)
    if result:
        result["candidate_id"] = candidate["id"]
        result["stage"] = 2
    return result


def _apply_resolution(
    trust, new_drawer_id: str, candidate_id: str, result: Dict, conflict_id: str, stage: int
):
    """Apply the LLM's verdict to the trust tables."""
    conflict_type = result.get("conflict_type", "none")
    winner = result.get("winner", "none")
    reason = result.get("reason", "")
    note = result.get("resolution_note", reason)

    if conflict_type == "none" or winner == "none":
        trust.resolve_conflict(conflict_id, "llm_no_conflict", note)
        return

    from .drawer_trust import STATUS_SUPERSEDED, STATUS_CONTESTED

    if winner == "b":
        trust.update_status(
            candidate_id,
            STATUS_SUPERSEDED,
            confidence=max(0.1, (trust.get(candidate_id) or {}).get("confidence", 1.0) - 0.3),
            superseded_by=new_drawer_id,
            reason=f"stage{stage}: {reason}",
            changed_by="llm",
        )
        trust.resolve_conflict(conflict_id, new_drawer_id, note)
        logger.info(f"[trust] {candidate_id} → superseded by {new_drawer_id} (stage {stage})")

    elif winner == "a":
        trust.update_status(
            new_drawer_id,
            STATUS_SUPERSEDED,
            confidence=0.3,
            superseded_by=candidate_id,
            reason=f"stage{stage}: lost to existing — {reason}",
            changed_by="llm",
        )
        trust.resolve_conflict(conflict_id, candidate_id, note)
        logger.info(
            f"[trust] {new_drawer_id} → superseded by existing {candidate_id} (stage {stage})"
        )

    else:
        trust.update_status(
            candidate_id,
            STATUS_CONTESTED,
            reason=f"stage{stage}: ambiguous conflict",
            changed_by="llm",
        )
        trust.update_status(
            new_drawer_id,
            STATUS_CONTESTED,
            reason=f"stage{stage}: ambiguous conflict",
            changed_by="llm",
        )
        logger.info(f"[trust] Both contested: {candidate_id} <-> {new_drawer_id}")


def run_detection_thread(
    new_drawer_id: str,
    new_text: str,
    wing: str,
    room: str,
    candidates: List[Dict[str, Any]],
    trust,
    hybrid_searcher,
):
    """
    Background thread: Stage 1 → optionally Stage 2 per candidate.
    Throttled: global cooldown + inter-request sleep keep LLM pressure minimal.
    """
    global _last_detection_time

    # Skip entirely if no LLM configured
    from .llm_backend import NullBackend, ManagedBackend

    backend = _get_backend()
    if isinstance(backend, NullBackend):
        return

    # Auto-start if the server is down and we have a managed backend
    if isinstance(backend, ManagedBackend) and not backend.ping():
        logger.info("LLM backend unreachable — attempting auto-start")
        if not backend.ensure_running():
            logger.warning("Auto-start failed — skipping detection for this drawer")
            return

    # Global cooldown
    with _rate_lock:
        now = time.monotonic()
        wait = GLOBAL_COOLDOWN_SEC - (now - _last_detection_time)
        if wait > 0:
            logger.debug(f"Detection cooldown: sleeping {wait:.0f}s")
            time.sleep(wait)
        _last_detection_time = time.monotonic()

    for candidate in candidates:
        try:
            time.sleep(INTER_REQUEST_SLEEP)

            s1 = stage1_check(new_text, candidate)
            if not s1:
                continue

            conflict_type = s1.get("conflict_type", "none")
            if conflict_type == "none":
                continue

            conf = s1.get("confidence", 0.0)
            conflict_id = trust.record_conflict(candidate["id"], new_drawer_id, conflict_type, conf)

            if conf >= STAGE1_THRESHOLD:
                s1["stage"] = 1
                _apply_resolution(trust, new_drawer_id, candidate["id"], s1, conflict_id, stage=1)
            else:
                context_snippets = []
                try:
                    hits_a = hybrid_searcher.search(candidate["text"][:300], n_results=3)
                    hits_b = hybrid_searcher.search(new_text[:300], n_results=3)
                    seen = {candidate["id"], new_drawer_id}
                    for h in hits_a + hits_b:
                        if h["id"] not in seen:
                            context_snippets.append(h["text"])
                            seen.add(h["id"])
                except Exception as e:
                    logger.warning(f"Context pull failed: {e}")

                s2 = stage2_resolve(new_text, candidate, context_snippets)
                if s2:
                    _apply_resolution(
                        trust, new_drawer_id, candidate["id"], s2, conflict_id, stage=2
                    )
                else:
                    from .drawer_trust import STATUS_CONTESTED

                    trust.update_status(
                        new_drawer_id,
                        STATUS_CONTESTED,
                        reason="stage2 unavailable",
                        changed_by="system",
                    )

        except Exception as e:
            logger.error(f"Contradiction detection error for {candidate.get('id')}: {e}")


def spawn_detection(
    new_drawer_id: str,
    new_text: str,
    wing: str,
    room: str,
    trust,
    hybrid_searcher,
    k: int = CANDIDATES_K,
):
    """
    Entry point from tool_add_drawer.
    Returns immediately — detection happens in a daemon thread.
    """
    # Fast-path: skip thread spawn if LLM is disabled
    from .llm_backend import NullBackend

    if isinstance(_get_backend(), NullBackend):
        return

    try:
        results = hybrid_searcher.search(new_text, wing=wing, n_results=k + 1)
        candidates = [
            {"id": r["id"], "text": r["text"]} for r in results if r["id"] != new_drawer_id
        ][:k]
    except Exception as e:
        logger.warning(f"Candidate search failed: {e}")
        return

    if not candidates:
        return

    t = threading.Thread(
        target=run_detection_thread,
        args=(new_drawer_id, new_text, wing, room, candidates, trust, hybrid_searcher),
        daemon=True,
        name=f"trust_{new_drawer_id[:12]}",
    )
    t.start()
    logger.debug(f"Detection thread started for {new_drawer_id} vs {len(candidates)} candidates")
