import json
import os
import threading
from pathlib import Path
from datetime import datetime

SESSION_FILE = Path(os.path.expanduser("~/.mnemion/session_history.json"))
MAX_HISTORY = 5
_history_lock = threading.Lock()

# Singleton JEPA model — loaded once, persists across calls
_JEPA_MODEL_CACHE = None
_JEPA_WEIGHTS_LOADED = False


def _get_jepa_predictor():
    """Lazy-load the JEPA LSTM predictor, loading saved weights if available."""
    global _JEPA_MODEL_CACHE, _JEPA_WEIGHTS_LOADED
    if _JEPA_MODEL_CACHE is None:
        import torch
        import torch.nn as nn

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        class LivePredictor(nn.Module):
            def __init__(self, input_dim=384, hidden_dim=256):
                super().__init__()
                self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
                self.out = nn.Linear(hidden_dim, input_dim)

            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                return self.out(lstm_out[:, -1, :])

        _JEPA_MODEL_CACHE = LivePredictor().to(device)

        # Load saved weights ONCE at init, not on every call
        jepa_path = Path(os.path.expanduser("~/.mnemion/jepa_predictor.pt"))
        if jepa_path.exists():
            try:
                _JEPA_MODEL_CACHE.load_state_dict(
                    torch.load(jepa_path, map_location=device)
                )
            except Exception:
                pass
        _JEPA_WEIGHTS_LOADED = True

    return _JEPA_MODEL_CACHE


def record_activity(drawer_id, embedding=None):
    """Log a drawer access to the session history. Thread-safe."""
    with _history_lock:
        history = []
        if SESSION_FILE.exists():
            try:
                with open(SESSION_FILE, "r") as f:
                    history = json.load(f)
            except Exception:
                pass

        entry = {
            "id": drawer_id,
            "timestamp": datetime.now().isoformat()
        }
        if embedding is not None:
            entry["embedding"] = embedding

        history.append(entry)
        # Keep last N
        history = history[-MAX_HISTORY:]

        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, "w") as f:
            json.dump(history, f)


def predict_next_context(current_embeddings):
    """
    Takes a list of recent embeddings and predicts the 'next' embedding.
    This can be used to pre-fetch or suggest Rooms.
    """
    if len(current_embeddings) < 2:
        return None

    import torch
    import torch.nn.functional as F

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    jepa = _get_jepa_predictor()

    z = torch.tensor(current_embeddings, dtype=torch.float32, device=device)  # (T, D)

    # Online micro-training step using recent history as self-supervised signal
    optimizer = torch.optim.Adam(jepa.parameters(), lr=0.005)
    jepa.train()

    for _ in range(5):
        optimizer.zero_grad()
        # Predict t from 0:t-1
        loss = 0
        for t in range(1, len(z)):
            x_seq = z[:t].unsqueeze(0)  # (1, t, D)
            y_target = z[t].unsqueeze(0)  # (1, D)
            y_pred = jepa(x_seq)
            loss += F.mse_loss(y_pred, y_target)

        if loss > 0:
            loss.backward()
            optimizer.step()

    # Save the actively adapting state
    jepa_path = Path(os.path.expanduser("~/.mnemion/jepa_predictor.pt"))
    jepa_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(jepa.state_dict(), jepa_path)

    # Inference: Predict the NEXT state given the entire sequence
    jepa.eval()
    with torch.no_grad():
        final_seq = z.unsqueeze(0)  # (1, T, D)
        prediction = jepa(final_seq).squeeze(0)  # (D)

    return prediction.cpu().tolist()
