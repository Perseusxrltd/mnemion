import sys
import torch
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from mnemion.lewm import groom_embeddings

def test_grooming():
    print("--- Testing SIGReg Grooming ---")

    # 1. Create a "collapsed" cluster (20 identical embeddings + tiny noise)
    D = 384
    N = 20
    base = torch.randn(1, D)
    noise = torch.randn(N, D) * 0.05
    collapsed = (base + noise).numpy().tolist()

    # Calculate initial similarity
    z = torch.tensor(collapsed)
    z_norm = torch.nn.functional.normalize(z, p=2, dim=1)
    sims = torch.mm(z_norm, z_norm.t())
    mask = ~torch.eye(N, dtype=torch.bool)
    avg_sim_before = sims[mask].mean().item()
    print(f"Average Similarity (Before): {avg_sim_before:.4f}")

    # 2. Groom them
    groomed = groom_embeddings(collapsed, iterations=20, lr=0.01, sigreg_weight=0.5)

    # 3. Calculate new similarity
    z_g = torch.tensor(groomed)
    z_g_norm = torch.nn.functional.normalize(z_g, p=2, dim=1)
    sims_g = torch.mm(z_g_norm, z_g_norm.t())
    avg_sim_after = sims_g[mask].mean().item()
    print(f"Average Similarity (After):  {avg_sim_after:.4f}")

    # 4. Check semantic drift (how far did we move from original?)
    # Cosine distance to original should be small
    cos_diff = 1 - torch.nn.functional.cosine_similarity(z, z_g).mean().item()
    print(f"Semantic Drift (Distance):   {cos_diff:.4f}")

    if avg_sim_after < avg_sim_before:
        print("\nSUCCESS: SIGReg spread out the embeddings.")
    else:
        print("\nFAILURE: SIGReg did not reduce similarity.")

    # Real assertions so pytest doesn't silently pass on failure
    assert avg_sim_after < avg_sim_before, (
        f"SIGReg did not reduce similarity: before={avg_sim_before:.4f}, after={avg_sim_after:.4f}"
    )
    assert cos_diff < 0.8, (
        f"Semantic drift too large: {cos_diff:.4f}"
    )

if __name__ == "__main__":
    test_grooming()
