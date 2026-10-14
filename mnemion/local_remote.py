"""Private host-operator sharing settings and a supervised public connection.

Memory credentials cannot reach this control plane. A provider failure never
stops the local API, and a reachability probe never sends a memory credential.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import time
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import psutil
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)

from . import local_state as state, process_identity
from .service.hosted_oauth import HostedOAuthSettings
from .version import __version__

PROBE_PATH = "/.well-known/mnemion-host"
PROBE_INTERVAL_SECONDS = 900
MINIMUM_CHECK_INTERVAL_SECONDS = 30
Mode = Literal["disabled", "ngrok", "proxy"]


def capabilities() -> dict:
    """Import the real native binding without opening a provider connection."""
    from importlib.metadata import version
    import ngrok

    if not callable(ngrok.SessionBuilder):
        raise RuntimeError("The packaged remote connection runtime is unavailable")
    return {"ngrok_sdk": version("ngrok"), "existing_https_proxy": True}


def origin(value: str) -> str:
    # Match the desktop/browser URL representation after the strict HTTPS check,
    # including expanded IPv6 and shorthand IPv4 supplied by an operator CLI.
    checked = HostedOAuthSettings.for_workspace(value, UUID(int=0)).origin
    return str(AnyHttpUrl(checked)).rstrip("/")


class RemoteOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Mode = "disabled"
    public_url: str | None = Field(default=None, max_length=2048)
    personal_sign_in: bool = True
    ngrok_authtoken: SecretStr | None = None

    @field_validator("public_url")
    @classmethod
    def public_origin(cls, value):
        return origin(value) if value is not None else None

    @field_validator("ngrok_authtoken")
    @classmethod
    def token(cls, value):
        if value is not None:
            text = value.get_secret_value()
            if not 16 <= len(text) <= 256 or any(not 33 <= ord(c) <= 126 for c in text):
                raise ValueError("Use the ngrok account authtoken without whitespace")
        return value


class RemoteChange(RemoteOptions):
    workspace_id: UUID
    expected_revision: str = Field(min_length=1, max_length=64)


class RemoteCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workspace_id: UUID
    expected_revision: str = Field(min_length=1, max_length=64)


class RemoteConfiguration(RemoteOptions):
    format: Literal[1] = 1
    workspace_id: UUID
    revision: UUID
    updated_at: str


def _record(root: Path, workspace_id: str):
    """Retain damaged private bytes for an explicitly revision-bound repair."""
    try:
        content = state.read_bytes(root / "remote-access.json")
    except FileNotFoundError:
        return None, None, "not-configured"
    try:
        saved = RemoteConfiguration.model_validate_json(content)
        if str(saved.workspace_id) != workspace_id:
            raise ValueError("Different workspace")
        if saved.mode != "disabled" and not saved.public_url:
            raise ValueError("Missing public origin")
        if saved.mode == "ngrok" and (
            saved.ngrok_authtoken is None or urlsplit(saved.public_url).port is not None
        ):
            raise ValueError("Invalid ngrok connection")
        if saved.mode != "ngrok" and saved.ngrok_authtoken is not None:
            raise ValueError("Unexpected provider credential")
        return saved, content, str(saved.revision)
    except (ValueError, ValidationError, RecursionError):
        return None, content, hashlib.sha256(content).hexdigest()


def public_configuration(saved: RemoteConfiguration | None, revision: str) -> dict:
    return {
        "mode": saved.mode if saved else "disabled",
        "public_url": saved.public_url if saved else None,
        "personal_sign_in": saved.personal_sign_in if saved else True,
        "has_ngrok_authtoken": bool(saved and saved.ngrok_authtoken),
        "revision": revision,
    }


def inspection(root: Path, workspace_id: str) -> dict:
    try:
        saved, content, revision = _record(root, workspace_id)
    except (OSError, state.LocalSetupError):
        return {
            **public_configuration(None, "unreadable"),
            "state": "configuration_error",
            "message": "Remote settings could not be read safely. Local access is retained.",
            "repairable": False,
        }
    view = public_configuration(saved, revision)
    if saved is None and content is not None:
        return {
            **view,
            "state": "configuration_error",
            "message": "Remote settings need repair. Saving preserves the damaged file and replaces only these settings.",
            "repairable": True,
        }
    view.update(
        state="disabled" if not saved or saved.mode == "disabled" else "unchecked",
        message="Remote access is off."
        if not saved or saved.mode == "disabled"
        else "No fresh route check is available. Start or refresh the local host.",
        repairable=True,
    )
    try:
        live = state.read(root / "runtime-remote.json")
        if (
            live["format"] == 1
            and live["revision"] == revision
            and 0 <= time.time() - live["sampled_at"] < 45
            and process_identity.matches(live["process_identity"], psutil.Process(live["pid"]))
        ):
            status = live["status"]
            # Runtime files are observations, never settings or authority.
            if isinstance(status, dict) and status.get("state") in {
                "connecting",
                "online",
                "unavailable",
                "stopped",
                "disabled",
            }:
                for name in ("state", "message", "checked_at", "verified_at", "provider_code"):
                    value = status.get(name)
                    if value is None or (isinstance(value, str) and len(value) <= 512):
                        view[name] = value
    except (OSError, KeyError, TypeError, ValueError, psutil.Error, state.LocalSetupError):
        pass
    return view


def configure(root: Path, change: RemoteChange) -> dict:
    from .local_workspace import configuration

    with state.lock(root):
        workspace = configuration(root)
        if str(change.workspace_id) != workspace["workspace_id"]:
            raise state.LocalSetupError("settings_changed", "Choose the current local workspace.")
        saved, content, revision = _record(root, workspace["workspace_id"])
        if change.expected_revision != revision:
            raise state.LocalSetupError(
                "settings_changed", "Remote settings changed. Refresh before saving them again."
            )
        token = None
        public = change.public_url if change.mode != "disabled" else None
        if change.mode != "disabled" and public is None:
            raise state.LocalSetupError("invalid_options", "Enter your public HTTPS address.")
        if change.mode == "ngrok":
            token = change.ngrok_authtoken or (saved.ngrok_authtoken if saved else None)
            if token is None or urlsplit(public).port is not None:
                raise state.LocalSetupError(
                    "invalid_options", "Enter your ngrok authtoken and HTTPS domain without a port."
                )
        updated = RemoteConfiguration(
            mode=change.mode,
            public_url=public,
            personal_sign_in=change.personal_sign_in,
            ngrok_authtoken=token,
            workspace_id=change.workspace_id,
            revision=uuid4(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        value = updated.model_dump(mode="json")
        value["ngrok_authtoken"] = token.get_secret_value() if token else None
        path = root / "remote-access.json"
        if content is not None and saved is None:
            state.replace_damaged(path, value, expected=content, kind="remote")
        else:
            state.write(path, value, replace=content is not None)
        return public_configuration(updated, str(updated.revision))


def request_check(root: Path, change: RemoteCheck) -> None:
    """Coalesce harmless check requests without acquiring the running host lock."""
    from .local_workspace import configuration

    workspace = configuration(root)
    saved, _, revision = _record(root, workspace["workspace_id"])
    if (
        str(change.workspace_id) != workspace["workspace_id"]
        or change.expected_revision != revision
    ):
        raise state.LocalSetupError(
            "settings_changed", "Remote settings changed. Refresh before checking them."
        )
    if not saved or saved.mode == "disabled":
        raise state.LocalSetupError(
            "remote_disabled", "Configure remote access before requesting a check."
        )
    state.write(
        root / "remote-check.json", {"format": 1, "revision": revision, "request": uuid4().hex}
    )


class RemoteAccess:
    """One owned provider session, with bounded anonymous route checks."""

    def __init__(self, root: Path, settings: dict, tenant_id: str, emit, *, transport=None):
        self.root, self.emit, self.transport = root, emit, transport
        self.endpoint = "http://127.0.0.1:" + str(settings["port"])
        self.view = inspection(root, settings["workspace_id"])
        self.settings = None
        if self.view["state"] != "configuration_error":
            self.settings, _, _ = _record(root, settings["workspace_id"])
        self.oauth = (
            HostedOAuthSettings.for_workspace(self.settings.public_url, UUID(tenant_id))
            if self.settings and self.settings.mode != "disabled" and self.settings.personal_sign_in
            else None
        )
        self.public_url = (
            self.settings.public_url if self.settings and self.settings.mode != "disabled" else None
        )
        self._proof_key = secrets.token_bytes(32)
        self._session = self._listener = None
        self._identity = process_identity.capture(psutil.Process())
        self._last_request = self.request_id()
        self._last_attempt = 0.0

    def request_id(self):
        try:
            record = state.read(self.root / "remote-check.json")
            if (
                record.get("format") == 1
                and record.get("revision") == self.view["revision"]
                and re.fullmatch(r"[a-f0-9]{32}", record.get("request", ""))
            ):
                return record["request"]
        except (OSError, TypeError, state.LocalSetupError):
            pass
        return None

    async def pause(self, seconds: float) -> None:
        until = time.monotonic() + seconds
        next_observation = time.monotonic() + 10
        requested = False
        while time.monotonic() < until:
            current = self.request_id()
            if current is not None and current != self._last_request:
                self._last_request, requested = current, True
            if (
                requested
                and time.monotonic() - self._last_attempt >= MINIMUM_CHECK_INTERVAL_SECONDS
            ):
                break
            if time.monotonic() >= next_observation:
                self.report(
                    self.view["state"],
                    self.view["message"],
                    provider_code=self.view.get("provider_code"),
                    checked=False,
                )
                next_observation = time.monotonic() + 10
            await asyncio.sleep(min(2, max(0, until - time.monotonic())))

    def proof(self, challenge: str) -> dict:
        return {
            "protocol": 1,
            "proof": hmac.new(self._proof_key, challenge.encode("ascii"), "sha256").hexdigest(),
        }

    def attach(self, app) -> None:
        if not self.public_url:
            return
        from fastapi import Query
        from starlette.responses import JSONResponse

        @app.get(PROBE_PATH, include_in_schema=False)
        def route(challenge: str = Query(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")):
            return JSONResponse(self.proof(challenge), headers={"Cache-Control": "no-store"})

    def report(self, status: str, message: str, *, provider_code=None, checked=True) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.view.update(state=status, message=message, provider_code=provider_code)
        if checked:
            self.view["checked_at"] = now
        if checked and status == "online":
            self.view["verified_at"] = now
        self.emit({"event": "remote_access", "remote_access": dict(self.view)})
        try:
            state.write(
                self.root / "runtime-remote.json",
                {
                    "format": 1,
                    "pid": os.getpid(),
                    "process_identity": self._identity,
                    "sampled_at": time.time(),
                    "revision": self.view["revision"],
                    "status": self.view,
                },
            )
        except (OSError, state.LocalSetupError):
            # A damaged cache cannot stop the API or expose a provider token.
            pass

    async def probe(self) -> None:
        challenge = secrets.token_hex(32)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8),
            follow_redirects=False,
            transport=self.transport,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "ngrok-skip-browser-warning": "1",
            },
        ) as client:
            async with client.stream(
                "GET", self.public_url + PROBE_PATH, params={"challenge": challenge}
            ) as response:
                if (
                    response.status_code != 200
                    or response.headers.get("content-encoding", "identity") != "identity"
                ):
                    raise ValueError("Public route is unavailable")
                body = bytearray()
                async for part in response.aiter_raw(chunk_size=512):
                    body.extend(part)
                    if len(body) > 2048:
                        raise ValueError("Public route did not return the bounded proof")
                if json.loads(body) != self.proof(challenge):
                    raise ValueError("Public route does not reach this process")

    async def connect(self) -> None:
        import ngrok

        self._session = await asyncio.wait_for(
            ngrok.SessionBuilder()
            .authtoken(self.settings.ngrok_authtoken.get_secret_value())
            .client_info("mnemion", __version__)
            .connect(),
            timeout=20,
        )
        self._listener = await asyncio.wait_for(
            self._session.http_endpoint()
            .domain(urlsplit(self.public_url).hostname)
            .scheme("https")
            .pooling_enabled(False)
            .listen_and_forward(self.endpoint),
            timeout=20,
        )
        if origin(self._listener.url()) != self.public_url:
            raise ValueError("Provider returned a different address")

    async def disconnect(self) -> None:
        session, self._session, self._listener = self._session, None, None
        if session is not None:
            try:
                await asyncio.wait_for(session.close(), timeout=5)
            except (Exception, asyncio.CancelledError):
                pass

    async def run(self) -> None:
        if not self.public_url:
            self.emit({"event": "remote_access", "remote_access": dict(self.view)})
            return
        failures = 0
        try:
            while True:
                self._last_attempt = time.monotonic()
                try:
                    if self.settings.mode == "ngrok" and self._listener is None:
                        self.report(
                            "connecting", "Opening your managed HTTPS connection…", checked=False
                        )
                        await self.connect()
                    await self.probe()
                    failures = 0
                    self.report("online", "The HTTPS address reaches this running workspace.")
                except Exception as error:
                    failures += 1
                    code = re.search(r"\bERR_NGROK_[0-9]{1,8}\b", str(error))
                    self.report(
                        "unavailable",
                        "Remote access could not be verified. Check the provider, domain and network. Local access is still available; Mnemion retries automatically.",
                        provider_code=code[0] if code else None,
                    )
                    if self.settings.mode == "ngrok" and (self._listener is None or failures >= 2):
                        await self.disconnect()
                # A free ngrok account has a monthly HTTP-request allowance.
                # Normal checks use ~2,880 requests in 30 days, not 86,400.
                delay = (
                    min(900, 30 * 2 ** min(failures - 1, 5)) if failures else PROBE_INTERVAL_SECONDS
                )
                await self.pause(delay)
        finally:
            await self.disconnect()
            self.report("stopped", "This host's remote connection is stopped.", checked=False)
