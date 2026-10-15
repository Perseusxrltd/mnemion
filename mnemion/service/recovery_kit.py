"""Create a portable encrypted recovery viewer without contacting a server."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..private_input import read_private
from ..private_output import private_output
from .recovery_directory import RecoveryDirectoryRecord, reference_url

FORMAT = "mnemion-recovery-kit-v1"
ITERATIONS = 600_000
TEMPLATE = Path(__file__).with_suffix(".html")


def payload(record: dict, *, endpoint: str, workspace_name: str) -> dict:
    if isinstance(record, dict) and "operation" in record:
        if record["operation"] != "recovery.directory" or not isinstance(
            record.get("result"), dict
        ):
            raise ValueError("Use the private recovery.directory result")
        record = record["result"]
    model = RecoveryDirectoryRecord.model_validate(record)
    if (model.revision == 0 and (model.updated_at is not None or model.updated_by is not None)) or (
        model.revision > 0 and (model.updated_at is None or model.updated_by is None)
    ):
        raise ValueError("Invalid recovery directory revision")
    if (
        not isinstance(workspace_name, str)
        or not 1 <= len(workspace_name.strip()) <= 256
        or any(ord(c) < 32 or ord(c) == 127 for c in workspace_name)
    ):
        raise ValueError("Use the verified workspace name")
    if not isinstance(endpoint, str) or len(endpoint) > 4096:
        raise ValueError("Use the verified workspace address")
    return {
        "format": FORMAT,
        "workspace_name": workspace_name.strip(),
        "endpoint": reference_url(endpoint, workspace=True),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        # A future response field must not silently enter an independent file.
        "record": model.model_dump(
            mode="json", include={"tenant_id", "revision", "updated_at", "updated_by", "directory"}
        ),
    }


def render_kit(record: dict, passphrase: str, *, endpoint: str, workspace_name: str) -> str:
    if (
        not isinstance(passphrase, str)
        or len(passphrase) < 15
        or len(passphrase.encode("utf-8")) > 4096
        or "\0" in passphrase
    ):
        raise ValueError("Use a separate recovery-kit passphrase of at least 15 characters")
    clear = json.dumps(
        payload(record, endpoint=endpoint, workspace_name=workspace_name),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(clear) > 16384:
        raise ValueError("The recovery kit exceeds its metadata limit")
    salt, nonce = os.urandom(32), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(
        passphrase.encode("utf-8")
    )
    cipher = AESGCM(key).encrypt(nonce, clear, FORMAT.encode("ascii"))

    def encoded(value):
        return base64.b64encode(value).decode("ascii")

    envelope = {
        "format": 1,
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-SHA256",
        "iterations": ITERATIONS,
        "salt": encoded(salt),
        "iv": encoded(nonce),
        "ciphertext": encoded(cipher),
    }
    html = TEMPLATE.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if html.count("__MNEMION_RECOVERY_DATA__") != 1 or html.count("__MNEMION_SCRIPT_HASH__") != 1:
        raise ValueError("The installed recovery viewer is incomplete")
    html = html.replace("__MNEMION_RECOVERY_DATA__", json.dumps(envelope, separators=(",", ":")))
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    if script is None:
        raise ValueError("The installed recovery viewer is incomplete")
    return html.replace(
        "__MNEMION_SCRIPT_HASH__", encoded(hashlib.sha256(script[1].encode("utf-8")).digest())
    )


def arguments(parser):
    parser.add_argument(
        "--record-file",
        type=Path,
        required=True,
        help="Private recovery.directory --result-file output or raw API response JSON",
    )
    parser.add_argument(
        "--passphrase-file",
        type=Path,
        required=True,
        help="Owner-only UTF-8 passphrase file; never a command-line secret",
    )
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--workspace-name", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New encrypted HTML kit; existing files are never replaced",
    )


def execute(args) -> int:
    try:
        # The control CLI's private JSON result may use escaped Unicode, which
        # is larger than the validated UTF-8 directory it contains.
        record = json.loads(read_private(args.record_file, maximum=32768))
        passphrase = read_private(args.passphrase_file, maximum=4096).decode("utf-8").rstrip("\r\n")
        html = render_kit(
            record, passphrase, endpoint=args.endpoint, workspace_name=args.workspace_name
        )
        with private_output(args.output) as output:
            output.write(html.encode("utf-8"))
        print(
            json.dumps(
                {
                    "created": True,
                    "output": str(args.output),
                    "encrypted": True,
                    "network_requests": 0,
                }
            )
        )
        return 0
    except (ValueError, OSError):
        # Validation errors can contain private field values; do not print them.
        print(
            json.dumps(
                {
                    "created": False,
                    "error": "Check the private record/passphrase files, verified address and workspace name, and choose a new output path. The passphrase needs at least 15 characters.",
                }
            )
        )
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    return execute(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
