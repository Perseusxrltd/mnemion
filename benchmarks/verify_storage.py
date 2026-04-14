import chromadb

COLLECTION_NAME = "mnemion_drawers"


def verify_storage():
    from mnemion.config import MnemionConfig

    client = chromadb.PersistentClient(path=MnemionConfig().anaktoron_path)
    col = client.get_collection(COLLECTION_NAME)

    # Fetch wing_stress
    results = col.get(where={"wing": "wing_stress"}, include=["embeddings", "documents"])

    ids = results.get("ids")
    embeddings = results.get("embeddings")

    print("--- Verification of wing_stress Storage ---")
    if not ids:
        print("No drawers found in wing_stress.")
        return

    for i in range(len(ids)):
        emb = embeddings[i][:5]
        print(f"ID: {ids[i]}")
        print(f"  Embedding (first 5): {emb}")


if __name__ == "__main__":
    verify_storage()
