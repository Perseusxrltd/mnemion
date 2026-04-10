#!/bin/bash
# Mnemion vLLM startup script
# Serves Gemma 4 locally for contradiction detection — no cloud, no API key.
#
# IMPORTANT: This script hardcodes PATH because WSL often inherits a broken
# Windows PATH (especially with nvm). Do not remove the export below.
#
# Configuration:
#   VLLM_MODEL   — path to your local model weights
#   VLLM_PORT    — port to serve on (default: 8000)
#   LOG          — log file path
#
# To start:  bash ~/run_vllm.sh &
# To check:  tail -f ~/vllm.log
# To stop:   pkill -f "vllm serve"

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

VLLM_MODEL="${VLLM_MODEL:-$HOME/models/gemma-4-E4B-it-FP8}"
VLLM_PORT="${VLLM_PORT:-8000}"
LOG="${LOG:-$HOME/vllm.log}"
VLLM_BIN="$HOME/vllm-env/bin/vllm"

# ── Resource limits ───────────────────────────────────────────────────────────
# GPU: 0.25 → ~8.5GB on a 34GB card. The 4B FP8 model uses ~4GB; rest is KV cache.
# Raising this makes inference faster but steals VRAM from games/other work.
GPU_UTIL="${GPU_UTIL:-0.25}"
# Max concurrent requests. 1 = sequential only, no batching, lowest GPU pressure.
MAX_SEQS="${MAX_SEQS:-1}"
# Context length. Our prompts are <1500 tokens so 4096 is plenty.
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"

# ── Validate ──────────────────────────────────────────────────────────────────
if [ ! -f "$VLLM_BIN" ]; then
    echo "[ERROR] vLLM not found at $VLLM_BIN"
    echo "Install: python3 -m venv ~/vllm-env && ~/vllm-env/bin/pip install vllm"
    exit 1
fi

if [ ! -d "$VLLM_MODEL" ]; then
    echo "[ERROR] Model not found at $VLLM_MODEL"
    echo "Set VLLM_MODEL=/path/to/your/model and retry"
    exit 1
fi

# ── Kill existing instance ────────────────────────────────────────────────────
pkill -f "vllm serve" 2>/dev/null && echo "[$(date '+%H:%M:%S')] Killed existing vLLM instance"
sleep 1

# ── Launch ────────────────────────────────────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting vLLM on port $VLLM_PORT" > "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Model: $VLLM_MODEL" >> "$LOG"

# nice -n 19  → lowest CPU priority (OS schedules it only when nothing else needs CPU)
# ionice -c 3 → idle I/O class (disk access only when no other process is waiting)
exec nice -n 19 ionice -c 3 \
  env VLLM_GPU_MEMORY_UTILIZATION="$GPU_UTIL" \
  "$VLLM_BIN" serve "$VLLM_MODEL" \
  --quantization compressed-tensors \
  --enable-prefix-caching \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs "$MAX_SEQS" \
  --port "$VLLM_PORT" \
  --host 0.0.0.0 \
  --trust-remote-code \
  --enforce-eager >> "$LOG" 2>&1
