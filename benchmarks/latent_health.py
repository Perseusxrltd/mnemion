import chromadb
import torch
import torch.nn.functional as F
import numpy as np

from mnemion.config import MnemionConfig
PALACE_PATH = MnemionConfig().anaktoron_path
COLLECTION_NAME = "mempalace_drawers"

def run_health_check(wing_name="wing_stress"):
    print(f"--- Mnemion Latent Health Check [{wing_name}] ---")

    client = chromadb.PersistentClient(path=PALACE_PATH)
    try:
        col = client.get_collection(COLLECTION_NAME)
    except Exception as e:
        print(f"Error: Collection '{COLLECTION_NAME}' not found. ({e})")
        return

    # 1. Fetch all embeddings for the wing
    results = col.get(
        where={"wing": wing_name},
        include=["embeddings", "metadatas", "documents"]
    )

    embeddings = results.get("embeddings")
    if embeddings is None or len(embeddings) < 2:
        print(f"Insufficient data in wing '{wing_name}' (count: {len(embeddings) if embeddings is not None else 0})")
        return

    print(f"Drawer IDs: {results.get('ids')}")
    z = torch.tensor(embeddings, dtype=torch.float32) # (N, D)
    N, D = z.shape
    print(f"Found {N} memories in '{wing_name}' (Embedding Dim: {D})")

    # 2. Calculate Cosine Similarity Distribution
    # Normalize for cosine similarity
    z_norm = F.normalize(z, p=2, dim=1)
    sim_matrix = torch.mm(z_norm, z_norm.t()) # (N, N)

    # Exclude diagonal
    mask = ~torch.eye(N, dtype=torch.bool)
    similarities = sim_matrix[mask]

    avg_sim = similarities.mean().item()
    max_sim = similarities.max().item()
    min_sim = similarities.min().item()
    std_sim = similarities.std().item()

    print("\nSimilarity Stats:")
    print(f"  Average: {avg_sim:.4f}")
    print(f"  Max:     {max_sim:.4f} (Closest pair)")
    print(f"  Min:     {min_sim:.4f} (Most diverse pair)")
    print(f"  Std Dev: {std_sim:.4f}")

    if avg_sim > 0.8:
        print("  WARNING: High average similarity detected. Latent space may be collapsing!")
    elif avg_sim < 0.2:
        print("  WARNING: Low average similarity. Memories might be too disconnected.")
    else:
        print("  STATUS: Latent space density looks healthy.")

    # 3. Simple SIGReg Normality Test (Distribution Check)
    # Project onto 100 random directions
    num_proj = 100
    A = torch.randn(D, num_proj)
    A = A / A.norm(p=2, dim=0, keepdim=True)

    # Projections: (N, num_proj)
    projections = torch.matmul(z, A)

    # Calculate Skewness and Kurtosis per projection (Normality indicators)
    def calc_stats(p):
        mean = p.mean()
        std = p.std()
        centered = p - mean
        skew = (centered**3).mean() / (std**3 + 1e-6)
        kurt = (centered**4).mean() / (std**4 + 1e-6) - 3.0
        return skew.abs().item(), kurt.abs().item()

    skews = []
    kurts = []
    for i in range(num_proj):
        s, k = calc_stats(projections[:, i])
        skews.append(s)
        kurts.append(k)

    avg_skew = np.mean(skews)
    avg_kurt = np.mean(kurts)

    print("\nSIGReg Normality Check (Lower is better):")
    print(f"  Average Skewness: {avg_skew:.4f}")
    print(f"  Average Kurtosis: {avg_kurt:.4f}")

    # 4. Comparative Stress Test Analysis
    if wing_name == "wing_stress":
        print("\n--- Comparative Stress Analysis ---")
        # Generate what the raw embeddings would look like (Ungroomed)
        raw_embs = []
        import hashlib
        contents = [
            "The concept of A is closely related to the logic of B.",
            "The concept of A is mostly related to the logic of B.",
            "The concept of A is strictly related to the logic of B.",
            "The concept of A is highly related to the logic of B.",
            "The concept of A is deeply related to the logic of B."
        ]
        for content in contents:
            torch.manual_seed(int(hashlib.md5(content.encode()).hexdigest(), 16) % 10**8)
            base = torch.ones(384) * 0.1
            noise = torch.randn(384) * 0.01
            raw_embs.append((base + noise).tolist())

        raw_z = torch.tensor(raw_embs)
        raw_z_norm = F.normalize(raw_z, p=2, dim=1)
        raw_sims = torch.mm(raw_z_norm, raw_z_norm.t())
        mask_raw = ~torch.eye(len(contents), dtype=torch.bool)
        avg_raw_sim = raw_sims[mask_raw].mean().item()

        print(f"  Ungroomed Similarity (Theoretical): {avg_raw_sim:.6f}")
        print(f"  Groomed Similarity (Actual Palace):  {avg_sim:.6f}")

        diff = avg_raw_sim - avg_sim
        if diff > 0:
            improvement = (diff / avg_raw_sim) * 100
            print(f"  RESULT: Latent space spread improved by {improvement:.4f}%")
        else:
            print("  RESULT: No improvement detected in spreading logic.")

if __name__ == "__main__":
    run_health_check()
