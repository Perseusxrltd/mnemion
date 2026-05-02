"""
chroma_compat.py — ChromaDB forward-compatibility helpers.

Ported from Perseusxrltd/mnemion upstream.
"""

import json
import logging
import os
import pickle
import shutil
import sqlite3

logger = logging.getLogger("mnemion.chroma_compat")


def _hnsw_dimensions_by_segment(anaktoron_path: str) -> dict[str, int]:
    db_path = os.path.join(anaktoron_path, "chroma.sqlite3")
    if not os.path.isfile(db_path):
        return {}
    try:
        with sqlite3.connect(db_path) as conn:
            segment_cols = {row[1] for row in conn.execute("PRAGMA table_info(segments)")}
            if {"scope", "type"}.issubset(segment_cols):
                where = "WHERE s.scope = 'VECTOR' OR s.type LIKE '%hnsw%'"
            else:
                where = ""
            rows = conn.execute(
                f"""
                SELECT s.id, c.dimension
                FROM segments s
                JOIN collections c ON c.id = s.collection
                {where}
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {segment_id: int(dimension) for segment_id, dimension in rows if dimension}


def fix_legacy_hnsw_metadata_pickle(anaktoron_path: str) -> None:
    """Convert legacy Chroma HNSW metadata pickles from dicts to PersistentData.

    Older persistent HNSW indexes stored ``index_metadata.pickle`` as a plain
    dict. Chroma 0.6.x loads that pickle and expects attributes such as
    ``dimensionality``. Convert in place, keeping a one-time sidecar backup.
    """
    if not os.path.isdir(anaktoron_path):
        return
    try:
        from chromadb.segment.impl.vector.local_persistent_hnsw import PersistentData
    except Exception as e:
        logger.warning("Could not import Chroma PersistentData for HNSW repair: %s", e)
        return

    dimensions_by_segment = _hnsw_dimensions_by_segment(anaktoron_path)
    repaired = 0
    for dirpath, _, filenames in os.walk(anaktoron_path):
        if "index_metadata.pickle" not in filenames:
            continue
        metadata_path = os.path.join(dirpath, "index_metadata.pickle")
        segment_id = os.path.basename(dirpath)
        try:
            with open(metadata_path, "rb") as f:
                payload = pickle.load(f)
            if not isinstance(payload, dict):
                dimension = getattr(payload, "dimensionality", None)
                repaired_dimension = dimensions_by_segment.get(segment_id)
                if dimension is None and repaired_dimension is not None:
                    backup_path = metadata_path + ".missing-dim.bak"
                    if not os.path.exists(backup_path):
                        shutil.copy2(metadata_path, backup_path)
                    payload.dimensionality = repaired_dimension
                    tmp_path = metadata_path + ".tmp"
                    with open(tmp_path, "wb") as f:
                        pickle.dump(payload, f)
                    os.replace(tmp_path, metadata_path)
                    repaired += 1
                continue

            dimension = payload.get("dimensionality") or dimensions_by_segment.get(segment_id)
            converted = PersistentData(
                dimensionality=dimension,
                total_elements_added=int(payload.get("total_elements_added") or 0),
                id_to_label=dict(payload.get("id_to_label") or {}),
                label_to_id=dict(payload.get("label_to_id") or {}),
                id_to_seq_id=dict(payload.get("id_to_seq_id") or {}),
            )
            converted.max_seq_id = payload.get("max_seq_id")

            backup_path = metadata_path + ".legacy-dict.bak"
            if not os.path.exists(backup_path):
                shutil.copy2(metadata_path, backup_path)
            tmp_path = metadata_path + ".tmp"
            with open(tmp_path, "wb") as f:
                pickle.dump(converted, f)
            os.replace(tmp_path, metadata_path)
            repaired += 1
        except Exception:
            logger.exception("Could not repair HNSW metadata pickle %s", metadata_path)
    if repaired:
        logger.info("Fixed %d legacy HNSW metadata pickle files in %s", repaired, anaktoron_path)


def fix_legacy_collection_config_json(anaktoron_path: str) -> None:
    """Add Chroma 0.6 collection config type tags missing from older DBs.

    Some existing Anaktoron databases have ``collections.config_json_str`` set
    to ``{}``. Chroma 0.6.x expects a ``_type`` discriminator before it can
    list or open collections, so patch the JSON before PersistentClient starts.
    """
    db_path = os.path.join(anaktoron_path, "chroma.sqlite3")
    if not os.path.isfile(db_path):
        return
    try:
        with sqlite3.connect(db_path) as conn:
            try:
                rows = conn.execute(
                    "SELECT rowid, config_json_str FROM collections"
                ).fetchall()
            except sqlite3.OperationalError:
                return

            updates = []
            for rowid, raw_config in rows:
                try:
                    config = json.loads(raw_config or "{}")
                except json.JSONDecodeError:
                    continue
                if not isinstance(config, dict):
                    continue
                changed = False
                if "_type" not in config:
                    config["_type"] = "CollectionConfigurationInternal"
                    changed = True
                hnsw_config = config.get("hnsw_configuration")
                if isinstance(hnsw_config, dict) and "_type" not in hnsw_config:
                    hnsw_config["_type"] = "HNSWConfigurationInternal"
                    changed = True
                if changed:
                    updates.append((json.dumps(config, separators=(",", ":")), rowid))

            if updates:
                conn.executemany(
                    "UPDATE collections SET config_json_str = ? WHERE rowid = ?",
                    updates,
                )
                logger.info("Fixed %d legacy collection config rows in %s", len(updates), db_path)
            conn.commit()
    except Exception:
        logger.exception("Could not fix collection config JSON in %s", db_path)


def fix_blob_seq_ids(anaktoron_path: str) -> None:
    """Fix ChromaDB 0.6.x → 1.5.x migration bug: BLOB seq_ids → INTEGER.

    ChromaDB 0.6.x stored seq_id as big-endian 8-byte BLOBs. ChromaDB 1.5.x
    expects INTEGER. The auto-migration doesn't convert existing rows, causing
    the Rust compactor to crash with "mismatched types; Rust type u64 (as SQL
    type INTEGER) is not compatible with SQL type BLOB".

    Must be called BEFORE chromadb.PersistentClient(path=anaktoron_path) so the
    fix lands before the compactor fires on init.

    Safe to call on a fresh 1.5.x Anaktoron — it checks typeof(seq_id) first
    and is a no-op when no BLOBs are found.
    """
    db_path = os.path.join(anaktoron_path, "chroma.sqlite3")
    if not os.path.isfile(db_path):
        return
    try:
        with sqlite3.connect(db_path) as conn:
            for table in ("embeddings",):
                try:
                    rows = conn.execute(
                        f"SELECT rowid, seq_id FROM {table} WHERE typeof(seq_id) = 'blob'"
                    ).fetchall()
                except sqlite3.OperationalError:
                    continue
                if not rows:
                    continue
                updates = [(int.from_bytes(blob, byteorder="big"), rowid) for rowid, blob in rows]
                conn.executemany(f"UPDATE {table} SET seq_id = ? WHERE rowid = ?", updates)
                logger.info("Fixed %d BLOB seq_ids in %s.%s", len(updates), db_path, table)
            conn.commit()
    except Exception:
        logger.exception("Could not fix BLOB seq_ids in %s", db_path)
