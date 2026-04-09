#!/usr/bin/env python3
"""
llm_backend.py — Pluggable LLM backend for MemPalace
=====================================================

Contradiction detection and future LLM features route through this module.
All backends expose a single method: chat(messages, max_tokens) -> Optional[str]

Supported backends:
  none        — disabled, contradiction detection silently skipped
  ollama      — local Ollama (http://localhost:11434)
  lmstudio    — local LM Studio (http://localhost:1234)
  vllm        — vLLM server, any host (default: localhost:8000)
  custom      — any OpenAI-compatible endpoint

All except 'none' and native Ollama use the OpenAI /v1/chat/completions format.
Ollama also supports this endpoint since v0.1.14; we try it first and fall back
to the native /api/generate format for older installs.

Configuration lives in ~/.mempalace/config.json under the "llm" key:
  {
    "llm": {
      "backend": "ollama",
      "url": "http://localhost:11434",
      "model": "gemma2:2b",
      "api_key": null
    }
  }
"""

import json
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Optional

logger = logging.getLogger("mempalace.llm")

# ── Default URLs ──────────────────────────────────────────────────────────────
BACKEND_DEFAULTS: Dict[str, Dict[str, str]] = {
    "ollama": {"url": "http://localhost:11434", "model": "gemma2:2b"},
    "lmstudio": {"url": "http://localhost:1234", "model": ""},
    "vllm": {"url": "http://localhost:8000", "model": ""},
    "custom": {"url": "", "model": ""},
}

BACKEND_LABELS = {
    "none": "None (disabled) — no conflict detection, saves instantly",
    "ollama": "Ollama          — local, easy setup: ollama pull gemma2",
    "lmstudio": "LM Studio       — local GUI with model browser",
    "vllm": "vLLM            — local, fast, needs GPU (WSL/Linux)",
    "custom": "Custom          — any OpenAI-compatible endpoint",
}


# ── Base class ────────────────────────────────────────────────────────────────


class LLMBackend:
    """Abstract LLM backend. Subclasses implement _do_chat."""

    name: str = "base"

    def chat(self, messages: List[Dict], max_tokens: int = 512) -> Optional[str]:
        """Send a chat request. Returns assistant text or None on failure."""
        raise NotImplementedError

    def ping(self) -> bool:
        """Quick connectivity check. Returns True if reachable."""
        raise NotImplementedError

    def info(self) -> str:
        """Human-readable description for status display."""
        raise NotImplementedError


class NullBackend(LLMBackend):
    """No-op backend — contradiction detection disabled."""

    name = "none"

    def chat(self, messages, max_tokens=512):
        return None

    def ping(self):
        return True

    def info(self):
        return "disabled (no LLM configured)"


# ── OpenAI-compatible backend (vLLM, LM Studio, Ollama ≥0.1.14, custom) ──────


class OpenAICompatBackend(LLMBackend):
    """Any OpenAI /v1/chat/completions compatible endpoint."""

    def __init__(
        self,
        url: str,
        model: str,
        api_key: Optional[str] = None,
        timeout: int = 60,
        name: str = "openai_compat",
    ):
        self.base_url = url.rstrip("/")
        self.endpoint = f"{self.base_url}/v1/chat/completions"
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.name = name

    def chat(self, messages: List[Dict], max_tokens: int = 512) -> Optional[str]:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.1,
            }
        ).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(self.endpoint, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
            logger.warning(f"[{self.name}] chat failed: {e}")
            return None

    def ping(self) -> bool:
        try:
            req = urllib.request.Request(
                f"{self.base_url}/v1/models",
                headers={"Authorization": f"Bearer {self.api_key or 'none'}"},
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False

    def info(self) -> str:
        return f"{self.name} @ {self.base_url}  model={self.model or '(auto)'}"


# ── Ollama native backend (fallback for pre-0.1.14) ──────────────────────────


class OllamaBackend(LLMBackend):
    """Ollama using /api/chat (messages format, supported since v0.1.14)."""

    name = "ollama"

    def __init__(
        self, url: str = "http://localhost:11434", model: str = "gemma2:2b", timeout: int = 120
    ):
        self.base_url = url.rstrip("/")
        self.model = model
        self.timeout = timeout
        # Try OpenAI-compat first; fall back to native
        self._compat = OpenAICompatBackend(url, model, timeout=timeout, name="ollama_compat")

    def chat(self, messages: List[Dict], max_tokens: int = 512) -> Optional[str]:
        # Try OpenAI-compat endpoint first (Ollama ≥0.1.14)
        result = self._compat.chat(messages, max_tokens)
        if result is not None:
            return result

        # Fall back to native /api/chat
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": 0.1},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["message"]["content"].strip()
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
            logger.warning(f"[ollama] chat failed: {e}")
            return None

    def ping(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5)
            return True
        except Exception:
            return False

    def info(self) -> str:
        return f"ollama @ {self.base_url}  model={self.model}"


# ── Factory ───────────────────────────────────────────────────────────────────


def get_backend(config=None) -> LLMBackend:
    """
    Build an LLMBackend from config. Pass a MempalaceConfig instance or None.
    Returns NullBackend if no LLM is configured.
    """
    if config is None:
        from .config import MempalaceConfig

        config = MempalaceConfig()

    llm_cfg = config.llm  # dict: {backend, url, model, api_key}
    backend_name = llm_cfg.get("backend", "none")

    if backend_name == "none" or not backend_name:
        return NullBackend()

    defaults = BACKEND_DEFAULTS.get(backend_name, {})
    url = llm_cfg.get("url") or defaults.get("url", "")
    model = llm_cfg.get("model") or defaults.get("model", "")
    api_key = llm_cfg.get("api_key") or None

    if backend_name == "ollama":
        return OllamaBackend(url=url, model=model)

    if backend_name in ("lmstudio", "vllm", "custom"):
        return OpenAICompatBackend(url=url, model=model, api_key=api_key, name=backend_name)

    logger.warning(f"Unknown LLM backend '{backend_name}' — using null")
    return NullBackend()
