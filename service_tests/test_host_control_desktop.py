"""Real Studio profile -> native engine -> independent SSH controller, API absent."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from mnemion.host_control import installation, lifecycle
from mnemion.host_control.desktop import execute
from mnemion.host_control.protocol import Operator, canonical
from mnemion.service import supervision
from service_tests.test_host_control_installation import (
    prepared_host as prepared_host,
    request,
    wait_until,
)


def test_private_desktop_pipe_validates_before_network_or_credential_output():
    public = execute(b'{"operation":"schema"}')
    assert "private_key" not in json.dumps(public)
    generated = execute(b'{"operation":"keygen"}')
    assert generated["public_key"].startswith("ssh-ed25519 ")
    for raw in (b'{"operation":"shell","command":"id"}', b"x" * 65537):
        with pytest.raises(ValueError):
            execute(raw)


def test_studio_profile_and_native_pipe_survive_reopen_with_the_memory_api_absent(
    prepared_host, tmp_path
):
    source = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    driver = source / "studio/electron/scripts/probe-host-client.mjs"
    if not node or not (source / "studio/electron/dist/host-profiles.js").is_file():
        if os.environ.get("MNEMION_REQUIRE_HOST_CLIENT_TESTS") == "1":
            pytest.fail("Required host-client acceptance needs the built desktop and Node")
        pytest.skip("Desktop profile journey runs after the required Studio build")
    service, control, _, _, port = prepared_host

    def desktop(action, **fields):
        completed = subprocess.run(
            [node, str(driver)],
            input=json.dumps(
                {
                    "root": str(tmp_path / "Desktop host logins"),
                    "python": sys.executable,
                    "source": str(source),
                    "action": action,
                    **fields,
                }
            ),
            capture_output=True,
            text=True,
            timeout=40,
            cwd=source,
        )
        result = json.loads(completed.stdout)
        assert completed.returncode == 0 and result["ok"], result
        assert "PRIVATE KEY" not in completed.stdout
        return result["result"]

    created = desktop("create")
    operator = Operator(name=created["name"], public_key=created["public_key"], role="custodian")
    adopted = installation.adopt(control, service, operator, port=port)
    try:
        assert lifecycle.start(control)["ready"]
        desktop("enroll", id=created["id"], connection=adopted["connection"])
        observed = desktop("inspect", id=created["id"])
        assert observed["status"]["ok"] and not observed["status"]["result"]["service"]["running"]
        stopped = desktop(
            "request",
            id=created["id"],
            request=json.loads(
                canonical(
                    request(
                        adopted["connection"], "service.stop", approve_service_interruption=True
                    ).model_dump(mode="json")
                )
            ),
        )
        assert stopped["ok"]
        operation_id = stopped["result"]["operation_id"]
        wait_until(
            lambda: (
                desktop("inspect", id=created["id"])["operation"]["result"]["phase"] == "succeeded"
            )
        )
        reopened = desktop("status")
        assert reopened["profiles"][0]["last_operation"]["request"]["request_id"] == operation_id
        assert reopened["profiles"][0]["last_operation"]["phase"] == "succeeded"
        assert not supervision.status(service)["running"]
    finally:
        assert lifecycle.stop(control)["stopped"]
