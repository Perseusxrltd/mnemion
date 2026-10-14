"""One worker-owned local model cache, with bounded authenticated loopback RPC."""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import secrets
import ssl
import tempfile
import threading
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import local_state
from ..private_output import private_output
from .embeddings import EmbeddedChunk, LocalEmbedder, vector_literal
from .errors import ServiceError

MAX_REQUEST = 6_010_000
MAX_RESPONSE = 16 * 1024 * 1024


def configure_managed_sharing(command: str) -> None:
    """Run in the current CLI, including when an older Supervisor launches it."""
    state = os.environ.get("MNEMION_SUPERVISED_STATE")
    role = os.environ.get("MNEMION_SUPERVISED_ROLE")
    if not state or {"serve": "api", "worker": "worker"}.get(command) != role:
        return
    sharing = os.environ.get("MNEMION_MODEL_SHARING", "1")
    if sharing not in {"0", "1"}:
        raise ValueError("MNEMION_MODEL_SHARING must be 0 or 1")
    if sharing == "1":
        os.environ["MNEMION_MODEL_BROKER"] = str(
            local_state.directory(Path(state)) / "model-broker"
        )
    else:
        os.environ.pop("MNEMION_MODEL_BROKER", None)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation: Literal["prepare", "query", "document", "count", "status"]
    generation: str = Field(pattern=r"^[a-f0-9]{64}$")
    text: str = Field(default="", max_length=1_000_000)


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format: Literal[1]
    port: int = Field(ge=1, le=65535)
    token: str = Field(pattern=r"^[a-f0-9]{64}$")
    certificate: str = Field(min_length=100, max_length=4096)


def server_identity(directory: Path) -> tuple[ssl.SSLContext, str]:
    """Pin the worker before sending text; a reused local port cannot impersonate it."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    key = Ed25519PrivateKey.generate()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mnemion local model worker")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False
        )
        .sign(key, None)
        .public_bytes(serialization.Encoding.PEM)
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with tempfile.TemporaryDirectory(prefix=".identity-", dir=directory) as temporary:
        staging = local_state.directory(Path(temporary))
        with private_output(staging / "key.pem") as stream:
            stream.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        with private_output(staging / "certificate.pem") as stream:
            stream.write(certificate)
        context.load_cert_chain(staging / "certificate.pem", staging / "key.pem")
    return context, certificate.decode("ascii")


def unavailable() -> ServiceError:
    return ServiceError(
        503, "embedding_unavailable", "The shared local model worker is unavailable."
    )


class BrokerServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, registry, token, context):
        self.registry, self.token = registry, token
        self.capacity = threading.BoundedSemaphore(32)
        super().__init__(("127.0.0.1", 0), BrokerHandler)
        self.socket = context.wrap_socket(
            self.socket, server_side=True, do_handshake_on_connect=False
        )

    def server_bind(self):
        # HTTPServer normally reverse-resolves its listening address here.
        # Darwin's resolver can stall in a daemonized managed service. This
        # private listener has a fixed numeric identity and never needs DNS.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address

    def process_request(self, request, client_address):
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.capacity.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.capacity.release()

    def handle_error(self, request, client_address):
        # Model failures and source text never reach the HTTP server's traceback.
        pass


class BrokerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, status, data):
        body = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
        if len(body) > MAX_RESPONSE:
            status, body = 503, b'{"error":"embedding_unavailable"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(body)

    def do_POST(self):
        authorization = self.headers.get_all("Authorization", [])
        if len(authorization) != 1 or not hmac.compare_digest(
            authorization[0].encode(), ("Bearer " + self.server.token).encode()
        ):
            return self.reply(401, {"error": "unauthorized"})
        if self.path != "/embedding" or self.headers.get("Transfer-Encoding"):
            return self.reply(400, {"error": "invalid_request"})
        sizes = self.headers.get_all("Content-Length", [])
        if len(sizes) != 1 or not sizes[0].isascii() or not sizes[0].isdigit() or len(sizes[0]) > 8:
            return self.reply(400, {"error": "invalid_request"})
        size = int(sizes[0])
        if not 1 <= size <= MAX_REQUEST:
            return self.reply(413, {"error": "request_too_large"})
        try:
            body = self.rfile.read(size)
            if len(body) != size:
                return self.reply(400, {"error": "invalid_request"})
            command = Request.model_validate_json(body)
            model = self.server.registry.get(command.generation)
            # A local sharing request must never enable a cloud provider.
            if not isinstance(model, LocalEmbedder) or isinstance(model, SharedLocalEmbedder):
                return self.reply(503, {"error": "embedding_profile_unavailable"})
            if command.operation == "status":
                from .resources import process_resources

                result = {
                    "scope": "indexing_worker",
                    "available": True,
                    "model_cache": self.server.registry.cache_status(),
                    "resources": process_resources(),
                    "inference": self.server.registry.inference_gate.snapshot(),
                }
            elif command.operation == "prepare":
                model.prepare()
                result = None
            elif command.operation == "count":
                result = model.token_count(command.text)
            elif not command.text:
                return self.reply(422, {"error": "invalid_request"})
            elif command.operation == "query":
                result = model.query(command.text)
            else:
                result = [
                    {"start": chunk.start, "end": chunk.end, "vector": chunk.vector}
                    for chunk in model.document(command.text)
                ]
            self.reply(200, {"generation": model.generation.id, "result": result})
        except (ValidationError, ValueError, json.JSONDecodeError):
            self.reply(422, {"error": "invalid_request"})
        except ServiceError as error:
            # Only bounded, public error codes cross the internal boundary.
            code = (
                error.code
                if error.code
                in {
                    "inference_busy",
                    "inference_memory_budget",
                    "query_too_long",
                    "embedding_profile_unavailable",
                }
                else "embedding_unavailable"
            )
            self.reply(422 if code == "query_too_long" else 503, {"error": code})
        except Exception:
            self.reply(503, {"error": "embedding_unavailable"})


class ModelBroker:
    def __init__(self, registry, directory: Path):
        self.registry, self.directory = registry, directory
        self.stack = ExitStack()

    def __enter__(self):
        try:
            local_state.directory(self.directory)
            self.stack.enter_context(local_state.lock(self.directory))
            self.token = secrets.token_hex(32)
            context, certificate = server_identity(self.directory)
            self.server = BrokerServer(self.registry, self.token, context)
            self.stack.callback(self.server.server_close)
            self.thread = threading.Thread(
                target=self.server.serve_forever,
                kwargs={"poll_interval": 0.1},
                name="mnemion-model-broker",
                daemon=True,
            )
            self.thread.start()
            self.stack.callback(self.thread.join, 2)
            self.stack.callback(self.server.shutdown)
            local_state.write(
                self.directory / "address.json",
                {
                    "format": 1,
                    "port": self.server.server_port,
                    "token": self.token,
                    "certificate": certificate,
                },
            )
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


class SharedLocalEmbedder(LocalEmbedder):
    """Same generation and spans; local inference always stays in the worker."""

    shared_model = True

    def __init__(self, directory: Path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.directory = directory
        self._client = None
        self._client_identity = None
        self._client_lock = threading.Lock()

    def _http(self, address):
        with self._client_lock:
            identity = (address.port, address.certificate)
            if self._client is None or self._client_identity != identity:
                if self._client is not None:
                    self._client.close()
                    self._client = None
                    self._client_identity = None
                context = ssl.create_default_context(cadata=address.certificate)
                self._client = httpx.Client(
                    verify=context,
                    timeout=httpx.Timeout(120, connect=2, write=10, pool=2),
                    trust_env=False,
                    follow_redirects=False,
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
                )
                self._client_identity = identity
            return self._client

    def close(self):
        with self._inference_gate.maintenance() as acquired:
            if acquired:
                with self._client_lock:
                    if self._client is not None:
                        self._client.close()
                        self._client = None
                        self._client_identity = None

    def _call(self, operation, text="", *, timeout=None):
        try:
            address = Address.model_validate(local_state.read(self.directory / "address.json"))
            body = json.dumps(
                {"operation": operation, "generation": self.generation.id, "text": text},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            if len(body) > MAX_REQUEST:
                raise ValueError("Bounded request exceeded")
            # The operator selects a private state directory, never a URL. DNS,
            # proxies and redirects cannot redirect memory to another machine.
            with self._http(address).stream(
                "POST",
                f"https://127.0.0.1:{address.port}/embedding",
                headers={
                    "Authorization": "Bearer " + address.token,
                    "Content-Type": "application/json",
                },
                content=body,
                **({"timeout": timeout} if timeout is not None else {}),
            ) as response:
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE:
                        raise ValueError("Bounded response exceeded")
                    chunks.append(chunk)
                result = json.loads(b"".join(chunks))
                if response.status_code != 200:
                    if response.status_code == 503 and result.get("error") == "inference_busy":
                        raise ServiceError(
                            503, "inference_busy", "Model capacity is busy; retry shortly."
                        )
                    if response.status_code == 422 and result.get("error") == "query_too_long":
                        raise ServiceError(
                            422,
                            "query_too_long",
                            "The semantic query exceeds this model's query budget.",
                        )
                    if (
                        response.status_code == 503
                        and result.get("error") == "inference_memory_budget"
                    ):
                        raise ServiceError(
                            503,
                            "inference_memory_budget",
                            "Model work is paused by the host RAM budget. Use lexical search or adjust the host budget.",
                        )
                    raise unavailable()
            if (
                not isinstance(result, dict)
                or set(result) != {"generation", "result"}
                or result["generation"] != self.generation.id
            ):
                raise ValueError("Mismatched generation")
            return result["result"]
        except ServiceError:
            raise
        except Exception:
            raise unavailable() from None

    def _prepare(self):
        self._call("prepare")

    def worker_status(self):
        from .insights_models import SharedModelWorkerSnapshot

        missing = {"scope": "indexing_worker", "available": False}
        # Observation must not compete with inference or reset its idle age.
        with self._inference_gate.maintenance() as acquired:
            if not acquired:
                return missing
            try:
                return SharedModelWorkerSnapshot.model_validate(
                    self._call("status", timeout=httpx.Timeout(1, connect=0.5, pool=0.1))
                ).model_dump()
            except (ServiceError, ValueError):
                return missing

    def _query(self, text):
        result = self._call("query", text)
        try:
            vector_literal(result, self.generation.dimensions)
        except (ValueError, TypeError):
            raise unavailable() from None
        return result

    def _document(self, text):
        result = self._call("document", text)
        try:
            if not isinstance(result, list) or not 1 <= len(result) <= 512:
                raise ValueError("Invalid chunks")
            chunks = []
            for item in result:
                start, end, vector = item["start"], item["end"], item["vector"]
                if (
                    type(start) is not int
                    or type(end) is not int
                    or not 0 <= start < end <= len(text)
                ):
                    raise ValueError("Invalid source span")
                vector_literal(vector, self.generation.dimensions)
                chunks.append(EmbeddedChunk(start, end, vector))
            return chunks
        except (KeyError, ValueError, TypeError):
            raise unavailable() from None

    def token_count(self, text):
        with self._inference_gate.acquire():
            result = self._call("count", text)
            if type(result) is not int or not 0 <= result <= 10000000:
                raise unavailable()
            return result
