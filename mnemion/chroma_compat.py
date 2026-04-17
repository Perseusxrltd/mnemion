"""
chroma_compat.py — ChromaDB forward-compatibility helpers.

Ported from Perseusxrltd/mnemion upstream.
"""

import logging
import os
import sqlite3

logger = logging.getLogger("mnemion.chroma_compat")


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
            for table in ("embeddings", "max_seq_id"):
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
