import os
import tempfile
import shutil
from mnemion.convo_miner import mine_convos
from mnemion.chroma_compat import make_persistent_client


def test_convo_mining():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "chat.txt"), "w") as f:
        f.write(
            "> What is memory?\nMemory is persistence.\n\n> Why does it matter?\nIt enables continuity.\n\n> How do we build it?\nWith structured storage.\n"
        )

    anaktoron_path = os.path.join(tmpdir, "anaktoron")
    mine_convos(tmpdir, anaktoron_path, wing="test_convos")

    client = make_persistent_client(anaktoron_path)
    col = client.get_collection("mnemion_drawers")
    assert col.count() >= 2

    # Verify search works
    results = col.query(query_texts=["memory persistence"], n_results=1)
    assert len(results["documents"][0]) > 0

    shutil.rmtree(tmpdir, ignore_errors=True)
