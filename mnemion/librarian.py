#!/usr/bin/env python3
"""
mnemion/librarian.py — Daily background Anaktoron tidy-up.

The Librarian runs once a day (typically overnight) and processes drawers
that were never reviewed by the local LLM — because vLLM was down at save
time, or the hooks were broken, or the drawer was bulk-imported.

What it does per drawer:
  1. Contradiction scan  — compare against similar existing drawers
  2. Room re-classification — if stuck in 'general', suggest a better room
  3. KG extraction  — pull entity→relation→entity triples into the graph

Throttled throughout: INTER_REQUEST_SLEEP between LLM calls, low GPU util,
idle_timeout auto-stops vLLM when done. Completely silent to the user.

Usage:
    mnemion librarian [--limit N] [--wing WING] [--dry-run]
    mnemion librarian --status

State file: ~/.mnemion/librarian_state.json
  {
    "last_run": "2026-04-11T03:00:00",
    "total_processed": 1234,
    "cursor_timestamp": "2026-04-10T22:00:00"   # drawers added before this are done
  }
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mnemion.librarian")

INTER_REQUEST_SLEEP = 8.0  # seconds between LLM calls — lower GPU pressure
DEFAULT_LIMIT = 50  # drawers per run
KG_EXTRACTION_PROMPT = """Extract factual triples from this memory fragment.
Return ONLY a JSON array of objects, each with keys: subject, relation, object.
Only include clear, verifiable facts. If none, return [].
Example: [{{"subject": "Mnemion", "relation": "version", "object": "3.2.8"}}]

Memory:
{text}"""

RECLASS_PROMPT = """This memory is stored in the 'general' room. Suggest a better room name.
Choose from: technical, planning, decision, project_fact, personal, preference,
             tech_fact, problem, milestone, documentation, emotional, identity.
Return ONLY the room name, nothing else. If 'general' is truly correct, return 'general'.

Memory:
{text}"""

VALID_ROOMS = {
    "technical",
    "planning",
    "decision",
    "project_fact",
    "personal",
    "preference",
    "tech_fact",
    "problem",
    "milestone",
    "documentation",
    "emotional",
    "identity",
    "general",
}

STATE_FILE = Path(os.path.expanduser("~/.mnemion/librarian_state.json"))


# ── State management ──────────────────────────────────────────────────────────


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_run": None, "total_processed": 0, "cursor_timestamp": None}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Drawer discovery ──────────────────────────────────────────────────────────


def _find_unprocessed(
    kg_path: str, limit: int, wing: Optional[str], cursor_ts: Optional[str]
) -> list:
    """
    Return drawers that have never been LLM-reviewed:
      - verifications = 0 AND challenges = 0 (never touched by LLM)
      - status = 'current' (still active)
    Ordered oldest-first so we make steady forward progress.
    Cursor skips drawers added before the last successful run.
    """
    conn = sqlite3.connect(kg_path)
    conn.row_factory = sqlite3.Row
    try:
        params: list = []
        sql = """
            SELECT drawer_id, wing, room, created_at
            FROM drawer_trust
            WHERE status = 'current'
              AND verifications = 0
              AND challenges = 0
        """
        if cursor_ts:
            sql += " AND created_at > ?"
            params.append(cursor_ts)
        if wing:
            sql += " AND wing = ?"
            params.append(wing)
        sql += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_drawer_text(collection, drawer_id: str) -> Optional[str]:
    """Fetch drawer content from ChromaDB."""
    try:
        result = collection.get(ids=[drawer_id], include=["documents"])
        if result["ids"]:
            return result["documents"][0]
    except Exception as e:
                logger.error(f"Suppressed error in execution: {e}")
    return None


# ── LLM tasks ─────────────────────────────────────────────────────────────────


def _extract_kg_triples(backend, text: str) -> list:
    """Ask LLM to extract entity triples from a drawer."""
    messages = [
        {"role": "user", "content": KG_EXTRACTION_PROMPT.format(text=text[:1500])},
    ]
    raw = backend.chat(messages, max_tokens=256)
    if not raw:
        return []
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    try:
        triples = json.loads(raw)
        if isinstance(triples, list):
            return [
                t
                for t in triples
                if isinstance(t, dict) and all(k in t for k in ("subject", "relation", "object"))
            ]
    except json.JSONDecodeError:
        pass
    return []


def _suggest_room(backend, text: str, current_room: str) -> Optional[str]:
    """Ask LLM to suggest a better room if drawer is in 'general'."""
    if current_room != "general":
        return None
    messages = [
        {"role": "user", "content": RECLASS_PROMPT.format(text=text[:800])},
    ]
    raw = backend.chat(messages, max_tokens=32)
    if not raw:
        return None
    suggestion = raw.strip().lower().split()[0] if raw.strip() else None
    return suggestion if suggestion in VALID_ROOMS and suggestion != "general" else None


# ── Main librarian run ────────────────────────────────────────────────────────


def run_librarian(
    limit: int = DEFAULT_LIMIT, wing: Optional[str] = None, dry_run: bool = False
) -> dict:
    """
    Process up to `limit` unreviewed drawers.
    Returns a summary dict for the diary entry.
    """
    from .config import MempalaceConfig
    from .llm_backend import get_backend, NullBackend, ManagedBackend
    from .hybrid_searcher import HybridSearcher
    from .drawer_trust import DrawerTrust
    from .knowledge_graph import KnowledgeGraph
    import chromadb

    cfg = MempalaceConfig()
    backend = get_backend(cfg)

    if isinstance(backend, NullBackend):
        return {"skipped": True, "reason": "No LLM backend configured"}

    # Auto-start vLLM if needed
    if isinstance(backend, ManagedBackend) and not backend.ping():
        logger.info("Librarian: starting LLM backend...")
        if not backend.ensure_running():
            return {"skipped": True, "reason": "LLM backend failed to start"}

    palace_path = cfg.palace_path
    kg_path = os.path.join(os.path.dirname(palace_path), "knowledge_graph.sqlite3")
    trust = DrawerTrust(kg_path)
    kg = KnowledgeGraph(kg_path)
    hybrid = HybridSearcher(palace_path=palace_path, kg_path=kg_path)

    client = chromadb.PersistentClient(path=palace_path)
    try:
        collection = client.get_collection(cfg.collection_name)
    except Exception as e:
        logger.error(f"Caught exception: {e}")
        return {"skipped": True, "reason": f"Collection '{cfg.collection_name}' not found"}

    state = _load_state()
    cursor_ts = state.get("cursor_timestamp")

    drawers = _find_unprocessed(kg_path, limit, wing, cursor_ts)
    if not drawers:
        logger.info("Librarian: nothing to process — Anaktoron is tidy.")
        return {"processed": 0, "note": "nothing to do"}

    logger.info(f"Librarian: processing {len(drawers)} drawers (dry_run={dry_run})")

    stats = {
        "processed": 0,
        "contradictions_found": 0,
        "reclassified": 0,
        "kg_triples_added": 0,
        "errors": 0,
        "last_ts": cursor_ts,
    }

    for drawer in drawers:
        drawer_id = drawer["drawer_id"]
        current_room = drawer.get("room", "general")
        drawer_wing = drawer.get("wing", "")
        created_at = drawer.get("created_at", "")

        text = _get_drawer_text(collection, drawer_id)
        if not text:
            stats["errors"] += 1
            continue

        try:
            # ── Task 1: Contradiction detection (re-uses existing logic) ──────
            from . import contradiction_detector as _cd

            candidates = []
            try:
                results = hybrid.search(text, wing=drawer_wing, n_results=3)
                candidates = [
                    {"id": r["id"], "text": r["text"]} for r in results if r["id"] != drawer_id
                ][:2]
            except Exception as e:
                logger.debug(f"Candidate search failed for {drawer_id}: {e}")

            for candidate in candidates:
                time.sleep(INTER_REQUEST_SLEEP)
                s1 = _cd.stage1_check(text, candidate)
                if s1 and s1.get("conflict_type", "none") != "none":
                    conf = s1.get("confidence", 0.0)
                    conflict_id = trust.record_conflict(
                        candidate["id"], drawer_id, s1["conflict_type"], conf
                    )
                    if not dry_run:
                        from .contradiction_detector import _apply_resolution

                        s1["stage"] = 1
                        _apply_resolution(
                            trust, drawer_id, candidate["id"], s1, conflict_id, stage=1
                        )
                    stats["contradictions_found"] += 1
                    logger.info(
                        f"  conflict: {drawer_id[:16]} vs {candidate['id'][:16]} ({s1['conflict_type']})"
                    )

            # ── Task 2: Room re-classification ────────────────────────────────
            time.sleep(INTER_REQUEST_SLEEP)
            new_room = _suggest_room(backend, text, current_room)
            if new_room and not dry_run:
                conn = sqlite3.connect(kg_path)
                try:
                    conn.execute(
                        "UPDATE drawer_trust SET room = ?, updated_at = ? WHERE drawer_id = ?",
                        (new_room, datetime.now(timezone.utc).isoformat(), drawer_id),
                    )
                    conn.execute(
                        "UPDATE drawers_fts SET room = ? WHERE drawer_id = ?",
                        (new_room, drawer_id),
                    )
                    conn.commit()
                finally:
                    conn.close()

                # Sync Fix: Push metadata to ChromaDB Vector Store
                try:
                    c_metadata = collection.get(ids=[drawer_id])["metadatas"][0]
                    c_metadata["room"] = new_room
                    collection.update(ids=[drawer_id], metadatas=[c_metadata])
                except Exception as e:
                    logger.error(f"Failed to sync re-classification to Chroma: {e}")
                
                stats["reclassified"] += 1
                logger.info(f"  reclassified {drawer_id[:16]}: general → {new_room}")

            # ── Task 3: KG extraction ─────────────────────────────────────────
            time.sleep(INTER_REQUEST_SLEEP)
            triples = _extract_kg_triples(backend, text)
            for triple in triples:
                if not dry_run:
                    try:
                        kg.add_triple(
                            subject=triple["subject"],
                            predicate=triple["relation"],
                            obj=triple["object"],
                            source_closet=drawer_id,
                        )
                        stats["kg_triples_added"] += 1
                    except Exception as e:
                        logger.error(f"Suppressed error in execution: {e}")

            # ── Task 4: Entity learning ───────────────────────────────────────
            if not dry_run:
                try:
                    from .entity_registry import EntityRegistry
                    registry = EntityRegistry.load()
                    new_entities = registry.learn_from_text(text)
                    if new_entities:
                        logger.info(
                            f"  learned {len(new_entities)} entities from {drawer_id[:16]}"
                        )
                except Exception as e:
                    logger.debug(f"Entity learning skipped: {e}")

            # ── Mark as verified (won't be picked up next run) ───────────────
            if not dry_run:
                trust.verify(drawer_id)

            stats["processed"] += 1
            stats["last_ts"] = created_at
            logger.info(f"  done: {drawer_id[:16]} ({stats['processed']}/{len(drawers)})")

        except Exception as e:
            logger.error(f"Error processing {drawer_id}: {e}")
            stats["errors"] += 1

    # Update state
    if not dry_run and stats["last_ts"]:
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        state["total_processed"] = state.get("total_processed", 0) + stats["processed"]
        state["cursor_timestamp"] = stats["last_ts"]
        _save_state(state)

    return stats


def show_status() -> None:
    """Print librarian state and how many drawers are pending."""
    from .config import MempalaceConfig

    state = _load_state()
    cfg = MempalaceConfig()
    kg_path = os.path.join(os.path.dirname(cfg.palace_path), "knowledge_graph.sqlite3")

    pending = []
    if os.path.exists(kg_path):
        pending = _find_unprocessed(
            kg_path, limit=99999, wing=None, cursor_ts=state.get("cursor_timestamp")
        )

    print("\nMnemion Librarian Status")
    print("-" * 40)
    print(f"  Last run:        {state.get('last_run') or 'never'}")
    print(f"  Total processed: {state.get('total_processed', 0)}")
    print(f"  Pending drawers: {len(pending)}")
    print(f"  State file:      {STATE_FILE}")
    print()
