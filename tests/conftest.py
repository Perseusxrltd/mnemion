"""
conftest.py — Shared fixtures for Mnemion tests.

Provides isolated Anaktoron and knowledge graph instances so tests never
touch the user's real data or leak temp files on failure.

HOME is redirected to a temp directory at module load time — before any
mnemion imports — so that module-level initialisations (e.g.
``_kg = KnowledgeGraph()`` in mcp_server) write to a throwaway location
instead of the real user profile.
"""

import os
import shutil
import uuid
from pathlib import Path

# ── Isolate HOME before any mnemion imports ──────────────────────────
_original_env = {}
_test_tmp_root = Path(os.environ.get("MNEMION_TEST_TMP_ROOT", Path.cwd() / ".tmp" / "pytest"))


def _make_temp_dir(prefix: str) -> str:
    _test_tmp_root.mkdir(parents=True, exist_ok=True)
    path = _test_tmp_root / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir()
    return str(path)


_session_tmp = _make_temp_dir("mnemion_session_")

for _var in ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH"):
    _original_env[_var] = os.environ.get(_var)

os.environ["HOME"] = _session_tmp
os.environ["USERPROFILE"] = _session_tmp
os.environ["HOMEDRIVE"] = os.path.splitdrive(_session_tmp)[0] or "C:"
os.environ["HOMEPATH"] = os.path.splitdrive(_session_tmp)[1] or _session_tmp

# Now it is safe to import mnemion modules that trigger initialisation.
import chromadb  # noqa: E402
import pytest  # noqa: E402

from mnemion.config import DRAWER_HNSW_METADATA, MnemionConfig  # noqa: E402
from mnemion.knowledge_graph import KnowledgeGraph  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_mcp_cache():
    """Reset the MCP server's cached ChromaDB client/collection between tests."""

    def _clear_cache():
        try:
            from mnemion import mcp_server

            mcp_server._client_cache = None
            mcp_server._collection_cache = None
        except (ImportError, AttributeError):
            pass

    _clear_cache()
    yield
    _clear_cache()


@pytest.fixture(scope="session", autouse=True)
def _isolate_home():
    """Ensure HOME points to a temp dir for the entire test session.

    The env vars were already set at module level (above) so that
    module-level initialisations are captured.  This fixture simply
    restores the originals on teardown and cleans up the temp dir.
    """
    yield
    for var, orig in _original_env.items():
        if orig is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = orig
    shutil.rmtree(_session_tmp, ignore_errors=True)


@pytest.fixture
def tmp_dir():
    """Create and auto-cleanup a temporary directory."""
    d = _make_temp_dir("mnemion_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def anaktoron_path(tmp_dir):
    """Path to an empty Anaktoron directory inside tmp_dir."""
    p = os.path.join(tmp_dir, "anaktoron")
    os.makedirs(p)
    return p


@pytest.fixture
def config(tmp_dir, anaktoron_path):
    """A MnemionConfig pointing at the temp Anaktoron."""
    cfg_dir = os.path.join(tmp_dir, "config")
    os.makedirs(cfg_dir)
    import json

    with open(os.path.join(cfg_dir, "config.json"), "w") as f:
        json.dump({"anaktoron_path": anaktoron_path}, f)
    return MnemionConfig(config_dir=cfg_dir)


@pytest.fixture
def collection(anaktoron_path):
    """A ChromaDB collection pre-seeded in the temp Anaktoron."""
    client = chromadb.PersistentClient(path=anaktoron_path)
    col = client.get_or_create_collection("mnemion_drawers", metadata=DRAWER_HNSW_METADATA)
    yield col
    client.delete_collection("mnemion_drawers")
    del client


@pytest.fixture
def seeded_collection(collection):
    """Collection with a handful of representative drawers."""
    collection.add(
        ids=[
            "drawer_proj_backend_aaa",
            "drawer_proj_backend_bbb",
            "drawer_proj_frontend_ccc",
            "drawer_notes_planning_ddd",
        ],
        documents=[
            "The authentication module uses JWT tokens for session management. "
            "Tokens expire after 24 hours. Refresh tokens are stored in HttpOnly cookies.",
            "Database migrations are handled by Alembic. We use PostgreSQL 15 "
            "with connection pooling via pgbouncer.",
            "The React frontend uses TanStack Query for server state management. "
            "All API calls go through a centralized fetch wrapper.",
            "Sprint planning: migrate auth to passkeys by Q3. "
            "Evaluate ChromaDB alternatives for vector search.",
        ],
        metadatas=[
            {
                "wing": "project",
                "room": "backend",
                "source_file": "auth.py",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-01T00:00:00",
            },
            {
                "wing": "project",
                "room": "backend",
                "source_file": "db.py",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-02T00:00:00",
            },
            {
                "wing": "project",
                "room": "frontend",
                "source_file": "App.tsx",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-03T00:00:00",
            },
            {
                "wing": "notes",
                "room": "planning",
                "source_file": "sprint.md",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-04T00:00:00",
            },
        ],
    )
    return collection


@pytest.fixture
def kg(tmp_dir):
    """An isolated KnowledgeGraph using a temp SQLite file."""
    db_path = os.path.join(tmp_dir, "test_kg.sqlite3")
    return KnowledgeGraph(db_path=db_path)


@pytest.fixture
def seeded_kg(kg):
    """KnowledgeGraph pre-loaded with sample triples."""
    kg.add_entity("Alice", entity_type="person")
    kg.add_entity("Max", entity_type="person")
    kg.add_entity("swimming", entity_type="activity")
    kg.add_entity("chess", entity_type="activity")

    kg.add_triple("Alice", "parent_of", "Max", valid_from="2015-04-01")
    kg.add_triple("Max", "does", "swimming", valid_from="2025-01-01")
    kg.add_triple("Max", "does", "chess", valid_from="2024-06-01")
    kg.add_triple("Alice", "works_at", "Acme Corp", valid_from="2020-01-01", valid_to="2024-12-31")
    kg.add_triple("Alice", "works_at", "NewCo", valid_from="2025-01-01")

    return kg
