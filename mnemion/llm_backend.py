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
  wsl:///home/user/run_vllm.sh      → run in configured WSL distro (default Ubuntu)
  wsl://Ubuntu//home/user/script.sh → run in named WSL distro (Windows)
  /home/user/run_vllm.sh            → run directly (Linux / macOS)
  C:\\models\\start.ps1 or server.exe → run natively on Windows
"""

import json
import logging
import os
import hashlib
from pathlib import Path
import sys
import threading
import time as _time
import urllib.request
import urllib.error
from typing import List, Dict, Optional

logger = logging.getLogger("mnemion.llm")

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

    def chat(
        self,
        messages: List[Dict],
        max_tokens: int = 512,
        response_format: Optional[Dict] = None,
    ) -> Optional[str]:
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

    def chat(self, messages, max_tokens=512, response_format=None):
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

    def chat(
        self,
        messages: List[Dict],
        max_tokens: int = 512,
        response_format: Optional[Dict] = None,
    ) -> Optional[str]:
        payload_data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.1,
        }
        if response_format:
            payload_data["response_format"] = response_format

        payload = json.dumps(payload_data).encode("utf-8")

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

    def chat(
        self,
        messages: List[Dict],
        max_tokens: int = 512,
        response_format: Optional[Dict] = None,
    ) -> Optional[str]:
        # Try OpenAI-compat endpoint first (Ollama ≥0.1.14)
        result = self._compat.chat(messages, max_tokens, response_format)
        if result is not None:
            return result

        # Fall back to native /api/chat
        payload_data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.1},
        }
        if response_format:
            if isinstance(response_format, dict) and response_format.get("type") == "json_object":
                payload_data["format"] = "json"

        payload = json.dumps(payload_data).encode("utf-8")
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
        startup_timeout: int = 300,
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
        self._idle_launch = None
        self._model_controller = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def chat(
        self,
        messages: List[Dict],
        max_tokens: int = 512,
        response_format: Optional[Dict] = None,
    ) -> Optional[str]:
        self._last_used = _time.monotonic()
        controller, activity = None, None
        try:
            if not self.start_script.startswith("wsl://"):
                controller = self._controller()
                activity = controller.begin_activity()
        except Exception:
            logger.warning("Model custody is busy or unavailable; the request was not started")
            return None
        try:
            result = super().chat(messages, max_tokens, response_format)
        finally:
            self._last_used = _time.monotonic()
            if controller is not None:
                try:
                    controller.end_activity(activity)
                except Exception:
                    # Retaining a lease prevents idle teardown while an old
                    # caller is still alive. Never clear another launch's lease.
                    logger.warning("Model activity custody could not be finalized")
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
            if self._owns_server():
                self._start_idle_watcher()
            return True
        if not self.start_script:
            logger.debug(f"[{self.name}] unreachable and no start_script configured")
            return False
        logger.info(f"[{self.name}] server down — launching {self.start_script}")
        try:
            self._launch()
        except Exception:
            logger.warning("Model launch failed; verify the private custody state and start script")
            return False
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

    def _controller(self):
        if self._model_controller is None:
            from .managed_model_process import ModelController

            # Private local custody, never an analytics or network identifier.
            configuration = [self.base_url, self.model, self._launch_command()]
            key = hashlib.sha256(json.dumps(configuration, ensure_ascii=True).encode()).hexdigest()
            self._model_controller = ModelController(
                Path.home() / ".mnemion" / "managed-models" / key
            )
        return self._model_controller

    def _owns_server(self):
        if self.start_script.startswith("wsl://"):
            return False
        try:
            return self._controller().owned()
        except Exception:
            return False

    def stop(self, *, automatic=False):
        """Stop only a verified native launch; external/guest custody is separate."""
        if self.start_script.startswith("wsl://"):
            logger.warning("WSL guest ownership is unverified; use its original process manager")
            return False
        try:
            return self._controller().stop(only_unused=automatic)
        except Exception:
            logger.warning("Model shutdown could not be verified; custody was retained")
            return False

    def info(self) -> str:
        base = super().info()
        if self.start_script.startswith("wsl://"):
            return f"{base}  WSL guest control requires its original process manager"
        if self.start_script:
            idle_min = self.idle_timeout // 60
            return (
                f"{base}  owned-model idle stop={idle_min}m"
                if self.idle_timeout > 0
                else f"{base}  idle stop disabled"
            )
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

    def _launch_command(self):
        """Resolve the actual target once per controller, without shell text."""
        if self.start_script.startswith("wsl://"):
            wsl_path = self._wsl_script_path()
            wsl_exe = self._wsl_exe()
            target = self.start_script[6:]
            distro = self.wsl_distro if target.startswith("/") else target.partition("/")[0]
            if not wsl_path.startswith("/") or not distro:
                raise ValueError("Choose an absolute WSL script path and a distribution")
            # A guest path is one argument, never shell text or permission to
            # rewrite the user's script. Guest scripts must use LF line endings.
            command = [wsl_exe, "-d", distro, "-e", "bash", wsl_path]
        else:
            script = str(Path(self.start_script).expanduser().absolute())
            if sys.platform == "win32" and Path(script).suffix.lower() == ".ps1":
                powershell = (
                    Path(os.environ.get("SystemRoot", r"C:\Windows"))
                    / "System32"
                    / "WindowsPowerShell"
                    / "v1.0"
                    / "powershell.exe"
                )
                command = [
                    str(powershell),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    script,
                ]
            elif sys.platform == "win32" and Path(script).suffix.lower() == ".exe":
                command = [script]
            else:
                command = ["bash", script]
        return command

    def _launch(self):
        """Launch one recorded, detached foreground-script process."""
        return self._controller().launch(self._launch_command())

    def _restart(self):
        """Stop then re-start the server."""
        if self.start_script.startswith("wsl://"):
            return False
        try:
            # Keep the controlled stop and relaunch atomic against another
            # operator. Never revive a model after a verified explicit stop.
            if not self._controller().restart(
                self._launch_command(), may_start=lambda: not self.ping()
            ):
                return False
        except Exception:
            logger.warning("Model restart could not acquire launch custody")
            return False
        deadline = _time.monotonic() + self.startup_timeout
        while _time.monotonic() < deadline:
            _time.sleep(3)
            if self.ping():
                logger.info(f"[{self.name}] restart successful")
                self._consecutive_failures = 0
                self._start_idle_watcher()
                return True
        logger.error(f"[{self.name}] restart failed after {self.startup_timeout}s")
        return False

    def _start_idle_watcher(self):
        """Start the idle-timeout watcher daemon thread (no-op if already running)."""
        if self.idle_timeout <= 0 or not self._owns_server():
            return
        try:
            launch = self._controller().launch_identity()
        except Exception:
            return
        if launch is None:
            return
        with self._lock:
            if self._idle_thread and self._idle_thread.is_alive() and self._idle_launch == launch:
                return
            t = threading.Thread(
                target=self._idle_loop,
                args=(launch,),
                daemon=True,
                name=f"llm_idle_{self.name}",
            )
            self._idle_thread = t
            self._idle_launch = launch
            t.start()
            logger.debug(f"[{self.name}] idle watcher started (timeout={self.idle_timeout}s)")

    def _idle_loop(self, launch):
        """Daemon loop: stop the server once it has been idle for idle_timeout seconds."""
        while True:
            _time.sleep(_IDLE_CHECK_INTERVAL)
            try:
                controller = self._controller()
                if not controller.owned(launch=launch) or controller.stop(
                    launch=launch, idle_seconds=self.idle_timeout
                ):
                    break
            except Exception:
                # Busy, unreadable or uncertain custody cannot authorize a kill.
                continue


# ── Factory ───────────────────────────────────────────────────────────────────


def get_backend(config=None) -> LLMBackend:
    """
    Build an LLMBackend from config. Pass a MnemionConfig instance or None.
    Returns NullBackend if no LLM is configured.
    Returns ManagedBackend when a start_script is present (enables auto-start/stop).
    """
    if config is None:
        from .config import MnemionConfig

        config = MnemionConfig()

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
        startup_timeout = int(llm_cfg.get("startup_timeout", 300))
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
