#!/usr/bin/env python3
"""
llm_backend.py — Pluggable LLM backend for Mnemion
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

Configuration lives in ~/.mnemion/config.json under the "llm" key:
  {
    "llm": {
      "backend": "vllm",
      "url": "http://172.25.x.x:8000",
      "model": "/home/user/models/my-model",
      "start_script": "wsl:///home/user/run_vllm.sh",
      "startup_timeout": 90,
      "idle_timeout": 300
    }
  }

start_script formats:
  wsl:///home/user/run_vllm.sh      → run in default WSL distro (Windows)
  wsl://Ubuntu//home/user/script.sh → run in named WSL distro (Windows)
  /home/user/run_vllm.sh            → run directly (Linux / macOS)
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time as _time
import urllib.request
import urllib.error
from typing import List, Dict, Optional

logger = logging.getLogger("mnemion.llm")

# ── Windows process flags for fully detached child processes ──────────────────
_DETACHED_FLAGS: int = 0
if sys.platform == "win32":
    _DETACHED_FLAGS = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

_IDLE_CHECK_INTERVAL = 30  # seconds between idle watcher ticks
_MAX_FAILURES = 3  # consecutive chat failures before auto-restart attempt

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


# ── Managed backend: auto-start / auto-stop / auto-restart ────────────────────


class ManagedBackend(OpenAICompatBackend):
    """
    OpenAI-compatible backend with full server lifecycle management.

    Behaviour:
    • ensure_running() — starts the server if it's down; blocks until ready
    • Auto-stop        — idle watcher kills the server after idle_timeout seconds
    • Auto-restart     — if chat() fails _MAX_FAILURES times in a row, the server
                         is stopped and re-launched automatically
    """

    def __init__(
        self,
        url: str,
        model: str,
        api_key: Optional[str] = None,
        timeout: int = 60,
        name: str = "vllm",
        start_script: str = "",
        startup_timeout: int = 90,
        idle_timeout: int = 300,
        wsl_distro: str = "Ubuntu",
    ):
        super().__init__(url, model, api_key, timeout, name)
        self.start_script = start_script
        self.startup_timeout = startup_timeout
        self.idle_timeout = idle_timeout
        self.wsl_distro = wsl_distro
        self._last_used: float = 0.0
        self._consecutive_failures: int = 0
        self._lock = threading.Lock()
        self._idle_thread: Optional[threading.Thread] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def chat(self, messages: List[Dict], max_tokens: int = 512) -> Optional[str]:
        self._last_used = _time.monotonic()
        result = super().chat(messages, max_tokens)
        if result is None:
            self._consecutive_failures += 1
            if self._consecutive_failures >= _MAX_FAILURES:
                logger.warning(
                    f"[{self.name}] {self._consecutive_failures} consecutive failures "
                    "— attempting restart"
                )
                self._restart()
        else:
            self._consecutive_failures = 0
        return result

    def ensure_running(self) -> bool:
        """
        Guarantee the server is up and ready. Starts it if not.
        Blocks until the server responds or startup_timeout is exceeded.
        Returns True when ready, False on timeout.
        """
        if self.ping():
            self._last_used = _time.monotonic()
            self._start_idle_watcher()
            return True
        if not self.start_script:
            logger.debug(f"[{self.name}] unreachable and no start_script configured")
            return False
        logger.info(f"[{self.name}] server down — launching {self.start_script}")
        self._launch()
        deadline = _time.monotonic() + self.startup_timeout
        while _time.monotonic() < deadline:
            _time.sleep(3)
            if self.ping():
                logger.info(f"[{self.name}] server ready")
                self._last_used = _time.monotonic()
                self._consecutive_failures = 0
                self._start_idle_watcher()
                return True
        logger.warning(f"[{self.name}] startup timed out after {self.startup_timeout}s")
        return False

    def stop(self):
        """Stop the server."""
        logger.info(f"[{self.name}] stopping server")
        try:
            if self.start_script.startswith("wsl://"):
                wsl_exe = self._wsl_exe()
                subprocess.run(
                    [wsl_exe, "-d", self.wsl_distro, "-e", "bash", "-c", "pkill -f 'vllm serve'"],
                    capture_output=True,
                    timeout=10,
                )
            else:
                subprocess.run(["pkill", "-f", "vllm serve"], capture_output=True, timeout=10)
        except Exception as e:
            logger.warning(f"[{self.name}] stop error: {e}")

    def info(self) -> str:
        base = super().info()
        if self.start_script:
            idle_min = self.idle_timeout // 60
            return f"{base}  auto-stop={idle_min}m"
        return base

    # ── Internal ───────────────────────────────────────────────────────────────

    def _wsl_script_path(self) -> str:
        """Extract the Linux path from a wsl:// URI."""
        path = self.start_script[6:]  # strip "wsl://"
        # wsl://DistroName//home/...  — strip distro name prefix
        if path and not path.startswith("/"):
            slash = path.find("/")
            path = path[slash:] if slash != -1 else path
        return path

    @staticmethod
    def _wsl_exe() -> str:
        candidate = r"C:\Windows\System32\wsl.exe"
        return candidate if os.path.exists(candidate) else "wsl.exe"

    def _launch(self):
        """Launch the start_script as a fully detached background process."""
        if self.start_script.startswith("wsl://"):
            wsl_path = self._wsl_script_path()
            wsl_exe = self._wsl_exe()
            if sys.platform == "win32":
                # wsl.exe with DETACHED_PROCESS creates an independent Windows
                # process; it keeps WSL alive for as long as vLLM runs.
                subprocess.Popen(
                    [wsl_exe, "-d", self.wsl_distro, "-e", "bash", wsl_path],
                    creationflags=_DETACHED_FLAGS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
            else:
                subprocess.Popen(
                    [wsl_exe, "-d", self.wsl_distro, "-e", "bash", wsl_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
        else:
            subprocess.Popen(
                ["bash", self.start_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

    def _restart(self):
        """Stop then re-start the server."""
        self.stop()
        _time.sleep(2)
        self._launch()
        deadline = _time.monotonic() + self.startup_timeout
        while _time.monotonic() < deadline:
            _time.sleep(3)
            if self.ping():
                logger.info(f"[{self.name}] restart successful")
                self._consecutive_failures = 0
                self._start_idle_watcher()
                return
        logger.error(f"[{self.name}] restart failed after {self.startup_timeout}s")

    def _start_idle_watcher(self):
        """Start the idle-timeout watcher daemon thread (no-op if already running)."""
        with self._lock:
            if self._idle_thread and self._idle_thread.is_alive():
                return
            t = threading.Thread(
                target=self._idle_loop,
                daemon=True,
                name=f"llm_idle_{self.name}",
            )
            self._idle_thread = t
            t.start()
            logger.debug(f"[{self.name}] idle watcher started (timeout={self.idle_timeout}s)")

    def _idle_loop(self):
        """Daemon loop: stop the server once it has been idle for idle_timeout seconds."""
        while True:
            _time.sleep(_IDLE_CHECK_INTERVAL)
            if not self.ping():
                logger.debug(f"[{self.name}] server gone — idle watcher exiting")
                break
            idle = _time.monotonic() - self._last_used
            if idle >= self.idle_timeout:
                logger.info(f"[{self.name}] idle {idle:.0f}s ≥ {self.idle_timeout}s — stopping")
                self.stop()
                break


# ── Factory ───────────────────────────────────────────────────────────────────


def get_backend(config=None) -> LLMBackend:
    """
    Build an LLMBackend from config. Pass a MempalaceConfig instance or None.
    Returns NullBackend if no LLM is configured.
    Returns ManagedBackend when a start_script is present (enables auto-start/stop).
    """
    if config is None:
        from .config import MempalaceConfig

        config = MempalaceConfig()

    llm_cfg = config.llm  # dict: {backend, url, model, api_key, ...}
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
        start_script = llm_cfg.get("start_script", "")
        startup_timeout = int(llm_cfg.get("startup_timeout", 90))
        idle_timeout = int(llm_cfg.get("idle_timeout", 300))
        wsl_distro = llm_cfg.get("wsl_distro", "Ubuntu")
        if start_script:
            return ManagedBackend(
                url=url,
                model=model,
                api_key=api_key,
                name=backend_name,
                start_script=start_script,
                startup_timeout=startup_timeout,
                idle_timeout=idle_timeout,
                wsl_distro=wsl_distro,
            )
        return OpenAICompatBackend(url=url, model=model, api_key=api_key, name=backend_name)

    logger.warning(f"Unknown LLM backend '{backend_name}' — using null")
    return NullBackend()
