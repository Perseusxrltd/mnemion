try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class _SIGReg(torch.nn.Module if TORCH_AVAILABLE else object):
    """
    Sketch Isotropic Gaussian Regularizer (SIGReg) for Mnemion.

    This module measures how much an embedding distribution deviates from
    an isotropic Gaussian. It can be used as a loss function to "groom"
    the latent space of the Anaktoron.
    """

    def __init__(self, knots=17, num_proj=1024):
        super().__init__()
        self.num_proj = num_proj
        # Integration knots for the Epps-Pulley test
        t = torch.linspace(0, 3, knots, dtype=torch.float32)
        dt = 3 / (knots - 1)
        weights = torch.full((knots,), 2 * dt, dtype=torch.float32)
        weights[[0, -1]] = dt
        window = torch.exp(-t.square() / 2.0)

        self.register_buffer("t", t)
        self.register_buffer("phi", window)
        self.register_buffer("weights", weights * window)

    def forward(self, z):
        """
        Compute SIGReg loss for a batch of embeddings.
        z: (N, D) tensor of embeddings.
        """
        N, D = z.shape
        if N < 2:
            return torch.tensor(0.0, device=z.device, requires_grad=True)

        # Sample random projections
        A = torch.randn(D, self.num_proj, device=z.device)
        A = A / A.norm(p=2, dim=0, keepdim=True)

        # Project embeddings: (N, M)
        proj = torch.matmul(z, A)

        # Compute the Epps-Pulley statistic
        x_t = proj.unsqueeze(-1) * self.t

        # Mean over memories N
        cos_mean = x_t.cos().mean(dim=0)  # (M, K)
        sin_mean = x_t.sin().mean(dim=0)  # (M, K)

        err = (cos_mean - self.phi).square() + sin_mean.square()
        statistic = torch.matmul(err, self.weights) * N

        return statistic.mean()


# Keep backward-compat name for tests that import SIGReg directly
SIGReg = _SIGReg


def groom_embeddings(embeddings, iterations=10, lr=0.01, sigreg_weight=0.1, dim=384, model_path=None):
    """
    Trains a lightweight Latent Adapter dynamically in the background to separate
    dense representations across the manifold without destroying baseline semantics.
    Returns the projected embeddings.

    Safe to call without torch installed — returns embeddings unchanged.
    """
    if not TORCH_AVAILABLE:
        return embeddings
    if len(embeddings) < 2:
        return embeddings

    import os

    class LatentAdapter(torch.nn.Module):
        def __init__(self, size=384):
            super().__init__()
            self.proj = torch.nn.Linear(size, size, bias=False)
            # Initialize to pristine identity - start with semantic perfection
            torch.nn.init.eye_(self.proj.weight)

        def forward(self, x):
            return self.proj(x)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    z = torch.tensor(embeddings, dtype=torch.float32, device=device)

    adapter = LatentAdapter(size=dim).to(device)
    if model_path and os.path.exists(model_path):
        try:
            adapter.load_state_dict(torch.load(model_path, map_location=device))
        except Exception:
            pass

    sigreg_mod = _SIGReg().to(device)
    optimizer = torch.optim.Adam(adapter.parameters(), lr=lr)

    # Fast background loop
    for _ in range(iterations):
        optimizer.zero_grad()

        # 1. Forward pass
        z_proj = adapter(z)

        # 2. Contrastive Preservation Loss (Maintain semantic structures)
        # We penalize distance from the perfectly semantic original embeddings
        loss_preserve = F.mse_loss(z_proj, z)

        # 3. SIGReg / Spreading
        # Add slight orthogonal spreading penalty
        z_norm = F.normalize(z_proj, p=2, dim=1)
        sim_matrix = torch.mm(z_norm, z_norm.t())
        mask = ~torch.eye(z_proj.size(0), dtype=torch.bool, device=device)
        loss_diversity = sim_matrix[mask].abs().mean()

        loss_sigreg = sigreg_mod(z_proj)

        # Objective: Stay highly semantic while forcing manifold spreading
        total_loss = loss_preserve + 0.1 * loss_diversity + sigreg_weight * loss_sigreg

        total_loss.backward()
        optimizer.step()

    # Save artifact
    if model_path:
        torch.save(adapter.state_dict(), model_path)

    # Return the newly projected (spread) semantic embeddings
    with torch.no_grad():
        final_proj = adapter(z)

    return final_proj.cpu().numpy().tolist()
