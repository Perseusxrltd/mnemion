"""Read bounded, non-secret setup status from an isolated CI desktop."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys


def public_status(value: object) -> dict:
    """Keep code locations and fixed states; exclude messages, paths and settings."""
    if not isinstance(value, dict):
        return {"available": False}
    result = {"available": True}
    for name, allowed in (
        ("state", {"new", "starting", "running", "stopping", "stopped", "error"}),
        (
            "stage",
            {"starting", "database", "backup", "migrate", "model", "service", "ready"},
        ),
    ):
        item = value.get(name)
        if isinstance(item, str) and item in allowed:
            result[name] = item
    code = value.get("errorCode")
    if (
        isinstance(code, str)
        and re.fullmatch(r"[a-z][a-z_]{0,63}", code)
        and not code.startswith("mnm_")
    ):
        result["error_code"] = code
    diagnostic = value.get("diagnostic")
    categories = {"unexpected", "memory", "dependency", "operating_system", "timeout", "database"}
    if (
        not isinstance(diagnostic, dict)
        or not isinstance(diagnostic.get("category"), str)
        or diagnostic["category"] not in categories
    ):
        return result
    safe = {"category": diagnostic["category"], "locations": []}
    for name in ("errno", "winerror"):
        number = diagnostic.get(name)
        if type(number) is int and 0 <= number <= 2**32 - 1:
            safe[name] = number
    sqlstate = diagnostic.get("sqlstate")
    if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
        safe["sqlstate"] = sqlstate
    locations = diagnostic.get("locations")
    for location in locations[:8] if isinstance(locations, list) else []:
        if not isinstance(location, dict):
            continue
        module, function, line = (location.get(name) for name in ("module", "function", "line"))
        if (
            isinstance(module, str)
            and re.fullmatch(r"mnemion(?:\.[a-z_][a-z0-9_]{0,63}){1,4}", module)
            and isinstance(function, str)
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", function)
            and "mnm_" not in module + function
            and type(line) is int
            and 1 <= line <= 1_000_000
        ):
            safe["locations"].append({"module": module, "function": function, "line": line})
    result["diagnostic"] = safe
    return result


def inspect_local_status(port: int | None, environment: dict) -> dict:
    if type(port) is not int or not 1024 <= port <= 65535:
        return {"available": False}
    # A fixed, read-only projection, using Node's built-in WebSocket. The debug
    # port is enabled only by the disposable installed probe and binds loopback.
    script = r"""
const port = process.argv[1];
let phase = 'http', pageCount = 0;
try {
const response = await fetch(`http://127.0.0.1:${port}/json/list`, {signal: AbortSignal.timeout(3000)});
const raw = await response.text();
if (!response.ok || raw.length > 65536) throw new Error('Unavailable');
phase = 'pages';
const pages = JSON.parse(raw).filter(item => item.type === 'page');
pageCount = pages.length;
if (pages.length !== 1) throw new Error('Unexpected page inventory');
phase = 'debugger';
const url = new URL(pages[0].webSocketDebuggerUrl);
if (url.protocol !== 'ws:' || url.hostname !== '127.0.0.1' || url.port !== port || url.username || url.password) throw new Error('Unexpected debugger');
phase = 'socket';
const result = await new Promise((resolve, reject) => {
  const socket = new WebSocket(url);
  const timer = setTimeout(() => { socket.close(); reject(new Error('Timeout')); }, 4000);
  socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Unavailable')); });
  socket.addEventListener('open', () => { phase = 'runtime'; socket.send(JSON.stringify({id: 1, method: 'Runtime.evaluate', params: {
    expression: '(async () => { const s = await window.mnemion.localStatus(); return {state:s.state,stage:s.stage,errorCode:s.errorCode,diagnostic:s.diagnostic}; })()',
    awaitPromise: true, returnByValue: true,
  }})); });
  socket.addEventListener('message', event => {
    if (typeof event.data !== 'string' || event.data.length > 131072) { clearTimeout(timer); socket.close(); reject(new Error('Too large')); return; }
    const message = JSON.parse(event.data);
    if (message.id !== 1) return;
    phase = message.error ? 'protocol' : message.result?.exceptionDetails ? 'javascript' : 'complete';
    clearTimeout(timer); socket.close(); resolve(message.result?.result?.value ?? null);
  });
});
process.stdout.write(JSON.stringify({phase, pageCount, status: result}));
} catch { process.stdout.write(JSON.stringify({phase, pageCount, status: null})); }
"""
    try:
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script, str(port)],
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        if result.returncode or len(result.stdout) > 128 * 1024:
            return {"available": False, "probe": "process"}
        envelope = json.loads(result.stdout)
        if not isinstance(envelope, dict):
            return {"available": False}
        evidence = public_status(envelope.get("status"))
        if isinstance(envelope.get("phase"), str) and envelope["phase"] in {
            "http",
            "pages",
            "debugger",
            "socket",
            "runtime",
            "protocol",
            "javascript",
            "complete",
        }:
            evidence["probe"] = envelope["phase"]
        count = envelope.get("pageCount")
        if type(count) is int and 0 <= count <= 32:
            evidence["page_count"] = count
        return evidence
    except subprocess.TimeoutExpired:
        return {"available": False, "probe": "process_timeout"}
    except (OSError, ValueError):
        return {"available": False, "probe": "process"}


MAC_STARTUP_SYMBOLS = (
    "SecItemCopyMatching",
    "SecKeychainFindGenericPassword",
    "SecKeychainItemCopyContent",
    "SecKeychainItemCopyAttributesAndData",
    "SecKeychainAddGenericPassword",
    "KeychainPassword",
    "GetEncryptionKey",
    "IsEncryptionAvailable",
    "EncryptString",
    "DecryptString",
    "xpc_connection_send_message_with_reply_sync",
    "mach_msg2_trap",
    "mach_msg_trap",
    "CFRunLoopRun",
    "uv_run",
    "BrowserMain",
    "ContentMain",
    "ElectronMain",
    "LaunchServices",
    "LSApplicationWorkspace",
)


def mac_startup_symbols(value: str) -> list[str]:
    # Only literal symbols from this allowlist leave the native sample. Never
    # export its arguments, environment, paths, memory or arbitrary stack text.
    return [symbol for symbol in MAC_STARTUP_SYMBOLS if symbol in value]


def inspect_mac_startup(pid: int, directory: Path, environment: dict) -> dict:
    if (
        sys.platform != "darwin"
        or type(pid) is not int
        or pid <= 0
        or os.environ.get("CI") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
        or os.environ.get("GITHUB_REPOSITORY") != "Perseusxrltd/mnemion"
    ):
        return {"available": False}
    import psutil

    result = {"available": False}
    try:
        result["security_agent_present"] = any(
            process.info.get("name") == "SecurityAgent" for process in psutil.process_iter(["name"])
        )
    except psutil.Error:
        pass
    path = directory / "macos-startup.private.sample"
    try:
        subprocess.run(
            ["/usr/bin/sample", str(pid), "1", "10", "-file", str(path)],
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if path.is_file() and path.stat().st_size <= 4 * 1024 * 1024:
            path.chmod(0o600)
            result.update(
                available=True,
                symbols=mac_startup_symbols(path.read_text(encoding="utf-8", errors="replace")),
            )
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result


def smoke_reason(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {}
    if isinstance(value.get("stage"), str) and value["stage"] in {
        "tray-ready",
        "backend-spawned",
        "backend-ready",
        "client-ready",
        "hosting-ready",
        "startup-error",
        "uncaught-exception",
        "unhandled-rejection",
        "backend-exit",
        "backend-timeout",
    }:
        result["smoke_stage"] = value["stage"]
    message = value.get("error")
    if not isinstance(message, str):
        return result
    for marker, reason in (
        ("did not open or automatically restore", "local_reopen_timeout"),
        ("Installed local setup failed", "local_setup_error"),
        ("Missing enabled control", "setup_control_missing"),
        ("has no authenticated local session", "local_session_missing"),
        ("A memory was lost", "saved_memory_missing"),
        ("did not retrieve the saved memory", "semantic_recall_missing"),
        ("RAM policy was not retained", "ram_policy_changed"),
    ):
        if marker in message:
            result["reason"] = reason
            break
    return result
