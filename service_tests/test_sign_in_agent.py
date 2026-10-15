"""Agent sign-in uses private files and never retries one-use credentials."""

import json
import os
from uuid import uuid4

import httpx
import psycopg
import pytest

from mnemion import control_cli
from mnemion.private_input import read_private
from mnemion.private_output import private_output
from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.sign_in import PasswordInput, SignInService
from service_tests.test_clients import running

PASSWORD = "cobalt prairie compass marble telescope"


def private_request(path, body):
    with private_output(path) as stream:
        stream.write(json.dumps({"body": body}).encode())
    return path


def login_body(workspace):
    return {
        "workspace_id": str(workspace),
        "username": "operator",
        "password": PASSWORD,
        "transport": "native",
        "device_name": "CLI fixture",
    }


def test_credential_operations_require_private_files_before_the_request(
    tmp_path, monkeypatch, capsys
):
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(200, json={})

    monkeypatch.setattr(
        control_cli,
        "Client",
        lambda *args, **kwargs: Client(*args, **kwargs, transport=httpx.MockTransport(response)),
    )
    request = private_request(tmp_path / "input.json", login_body(uuid4()))
    result = tmp_path / "result.json"
    command = ["--url", "https://workspace.invalid", "call", "sign_in.login"]
    for argv, expected in (
        (command, "private_input_required"),
        ([*command, "--input", "-"], "private_input_required"),
        ([*command, "--input", str(request)], "private_result_required"),
    ):
        assert control_cli.main(argv) == 1
        output = capsys.readouterr().out
        assert expected in output and PASSWORD not in output
    result.write_text("Preserve existing content")
    assert control_cli.main([*command, "--input", str(request), "--result-file", str(result)]) == 1
    assert result.read_text() == "Preserve existing content" and calls == []
    assert PASSWORD not in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode rejection; native ACL cases are separate")
def test_shared_password_file_is_not_sent(tmp_path, monkeypatch, capsys):
    request = private_request(tmp_path / "shared.json", login_body(uuid4()))
    request.chmod(0o644)
    monkeypatch.setattr(
        control_cli, "Client", lambda *args, **kwargs: pytest.fail("Unprotected input was sent")
    )
    assert (
        control_cli.main(
            [
                "--url",
                "https://workspace.invalid",
                "call",
                "sign_in.login",
                "--input",
                str(request),
                "--result-file",
                str(tmp_path / "result.json"),
            ]
        )
        == 1
    )
    assert PASSWORD not in capsys.readouterr().out


@pytest.mark.parametrize(
    "operation",
    [
        "sign_in.login",
        "sign_in.refresh",
        "sign_in.accept_invitation",
        "company.start",
        "company.finish",
    ],
)
def test_uncertain_credential_writes_do_not_retry_or_print_remote_content(
    tmp_path, monkeypatch, capsys, operation
):
    calls = []
    secret = "mnm_r_" + "x" * 43
    body = {
        "sign_in.login": login_body(uuid4()),
        "sign_in.refresh": {
            "workspace_id": str(uuid4()),
            "session_id": str(uuid4()),
            "transport": "native",
            "refresh_token": secret,
        },
        "sign_in.accept_invitation": {
            "invitation": "mnm_i_" + "x" * 43,
            "username": "operator",
            "password": PASSWORD,
            "transport": "native",
            "device_name": "CLI fixture",
        },
        "company.start": {
            "workspace_id": str(uuid4()),
            "provider_id": "company",
            "device_name": "CLI fixture",
            "transport": "native",
            "callback_uri": "http://127.0.0.1:45123/mnemion-company/" + "x" * 43,
        },
        "company.finish": {
            "state": "mnm_o_" + "x" * 43,
            "code_verifier": "x" * 43,
            "code": secret,
            "transport": "native",
        },
    }[operation]

    def response(request):
        calls.append(request)
        assert "authorization" not in request.headers
        return httpx.Response(503, json={"error": {"message": PASSWORD + secret}})

    monkeypatch.setenv("MNEMION_API_KEY", "unrelated-environment-key")
    monkeypatch.setattr(
        control_cli,
        "Client",
        lambda *args, **kwargs: Client(*args, **kwargs, transport=httpx.MockTransport(response)),
    )
    request = private_request(tmp_path / "input.json", body)
    output = tmp_path / "result.json"
    assert (
        control_cli.main(
            [
                "--url",
                "https://workspace.invalid",
                "call",
                operation,
                "--input",
                str(request),
                "--result-file",
                str(output),
                "--retries",
                "5",
            ]
        )
        == 1
    )
    report = capsys.readouterr().out
    assert len(calls) == 1 and not output.exists()
    assert PASSWORD not in report and secret not in report
    assert json.loads(report)["error"]["outcome"] == "unknown"
    assert json.loads(report)["error"]["retryable"] is False


def test_agent_can_create_login_refresh_and_revoke_with_real_workspace_authority(
    env, tmp_path, monkeypatch, capsys
):
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute("DELETE FROM mnemion.sign_in_attempts")
    SignInService(env.db).set_password(
        env.owner, PasswordInput(username="operator", password=PASSWORD)
    )
    monkeypatch.delenv("MNEMION_API_KEY", raising=False)
    with running(create_app(env.db, env.embedder, mcp_enabled=False)) as url:
        request = private_request(tmp_path / "login.json", login_body(env.owner.tenant_id))
        issued_path = tmp_path / "session.json"
        assert (
            control_cli.main(
                [
                    "--url",
                    url,
                    "call",
                    "sign_in.login",
                    "--input",
                    str(request),
                    "--result-file",
                    str(issued_path),
                ]
            )
            == 0
        )
        report = capsys.readouterr().out
        issued = json.loads(read_private(issued_path))
        assert issued["api_key"] == issued["access_token"]
        assert issued["tenant_id"] == str(env.owner.tenant_id)
        assert PASSWORD not in report and issued["refresh_token"] not in report
        assert issued["access_token"] not in report
        assert (
            control_cli.main(
                [
                    "--credentials",
                    str(issued_path),
                    "call",
                    "identity.me",
                ]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out)["result"]["principal_id"] == str(
            env.owner.principal_id
        )
        refresh = private_request(
            tmp_path / "refresh.json",
            {
                "workspace_id": issued["tenant_id"],
                "session_id": issued["session_id"],
                "transport": "native",
                "refresh_token": issued["refresh_token"],
            },
        )
        renewed_path = tmp_path / "renewed.json"
        assert (
            control_cli.main(
                [
                    "--url",
                    url,
                    "call",
                    "sign_in.refresh",
                    "--input",
                    str(refresh),
                    "--result-file",
                    str(renewed_path),
                ]
            )
            == 0
        )
        capsys.readouterr()
        renewed = json.loads(read_private(renewed_path))
        assert renewed["session_id"] == issued["session_id"]
        assert renewed["rotation"] == issued["rotation"] + 1
        with pytest.raises(ServiceError):
            env.db.authenticate(issued["access_token"])
        logout = private_request(
            tmp_path / "logout.json",
            {
                "workspace_id": renewed["tenant_id"],
                "session_id": renewed["session_id"],
                "transport": "native",
                "refresh_token": renewed["refresh_token"],
            },
        )
        assert (
            control_cli.main(
                [
                    "--url",
                    url,
                    "call",
                    "sign_in.logout",
                    "--input",
                    str(logout),
                    "--result-file",
                    str(tmp_path / "logout-receipt.json"),
                ]
            )
            == 0
        )
        report = capsys.readouterr().out
        assert renewed["refresh_token"] not in report
        with pytest.raises(ServiceError):
            env.db.authenticate(renewed["access_token"])
        assert env.db.authenticate(env.token) == env.owner
