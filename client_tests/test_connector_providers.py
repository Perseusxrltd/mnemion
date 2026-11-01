import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from mnemion.connectors.config import (
    ConnectorConfig,
    DriveConfig,
    FilesystemConfig,
    GitConfig,
    RcloneConfig,
    SlackConfig,
    Token,
    read_config,
)
from mnemion.connectors.extract import spreadsheet
from mnemion.connectors.gdrive import DriveProvider
from mnemion.connectors.providers import (
    FilesystemProvider,
    GitProvider,
    ProviderError,
    RcloneProvider,
    command,
)
from mnemion.connectors.slack import SlackProvider


def published(**kwargs):
    return {
        "scope_id": "company-vault",
        "name": "Company vault",
        "members": ["user:alice"],
        "publish_to_mapped_members": True,
        **kwargs,
    }


def test_provider_commands_stop_on_output_limit_and_timeout_without_exposing_stderr():
    assert command([sys.executable, "-c", "print('complete')"], maximum=100).strip() == b"complete"
    with pytest.raises(ProviderError, match="output_too_large"):
        command(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x'*10000000)"],
            maximum=1024,
        )
    with pytest.raises(ProviderError, match="command_unavailable"):
        command([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2)
    with pytest.raises(ProviderError) as exc:
        command(
            [
                sys.executable,
                "-c",
                "import sys; print('PRIVATE_PROVIDER_DIAGNOSTIC', file=sys.stderr); sys.exit(2)",
            ]
        )
    assert "PRIVATE_PROVIDER_DIAGNOSTIC" not in str(exc.value)


def test_portable_filesystem_preserves_text_and_hashes_and_excludes_settings(tmp_path):
    vault = tmp_path / "Café 漢字 vault"
    vault.mkdir()
    (vault / "Décision.md").write_bytes("# Décision\r\n\r\n[[Project]] uses Postgres.\r\n".encode())
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian/app.json").write_text('{"private":"configuration"}')
    (vault / "credentials.json").write_text('{"token":"never import"}')
    (vault / "Generated.md").write_text("---\nmnemion_managed: true\n---\nOld exported memory")
    provider = FilesystemProvider(FilesystemConfig(path=vault, **published()))
    docs = [doc for doc in provider.documents(provider.scopes()[0]) if doc]
    assert [doc.title for doc in docs] == ["Décision.md"]
    assert "\r\n" in docs[0].text and "[[Project]]" in docs[0].text
    assert (
        docs[0].metadata["original_sha256"]
        == hashlib.sha256((vault / "Décision.md").read_bytes()).hexdigest()
    )
    item = list(docs[0].items())[0]
    assert item.memory.source.content == docs[0].text
    assert item.memory.claim_status == "observed"
    assert item == list(docs[0].items())[0]


def test_folder_symlink_cannot_escape_selected_vault_or_certify_deletions(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.md").write_text("Private material")
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or privilege")
    provider = FilesystemProvider(FilesystemConfig(path=root, **published()))
    from mnemion.connectors.protocol import Document, SkippedDocument

    results = list(provider.documents(provider.scopes()[0]))
    assert not any(
        isinstance(value, Document) and "Private material" in value.text for value in results
    )
    stopped = [value for value in results if isinstance(value, SkippedDocument)]
    assert len(stopped) == 1
    assert stopped[0].abort_inventory
    assert stopped[0].code == "source_symlinks_not_supported"
    assert stopped[0].path == "linked"
    rendered = repr(results)
    assert "Private material" not in rendered
    assert str(outside) not in rendered
    receipt = stopped[0].report()
    assert receipt["error_code"] == "source_symlinks_not_supported"
    assert receipt["path"] == "linked"
    assert receipt["path_sha256"] == hashlib.sha256(b"linked").hexdigest()


def test_unreadable_directory_keeps_a_safe_category_and_omits_an_unsafe_path(tmp_path, monkeypatch):
    """Not run on 1 November 2026. A listing failure is a receipt, not an empty catalog."""
    import errno

    from mnemion.connectors import providers
    from mnemion.connectors.protocol import Document, SkippedDocument

    root = tmp_path / "vault"
    root.mkdir()
    (root / "a-kept.md").write_text("Permitted source")
    nested = root.resolve() / "nested"
    outside = tmp_path / "outside-secret"
    outside.mkdir()
    seen = {"unsafe": False}

    def walk(top, onerror=None, followlinks=False):
        if onerror is None:
            return
        if not seen["unsafe"]:
            onerror(PermissionError(errno.EACCES, "PRIVATE_OS_STRING", str(nested)))
        else:
            hidden = outside / "hidden"
            onerror(PermissionError(errno.EACCES, "PRIVATE_OS_STRING", str(hidden)))
        if False:
            yield top, [], []

    monkeypatch.setattr(providers.os, "walk", walk)
    provider = FilesystemProvider(FilesystemConfig(path=root, **published()))
    safe = list(provider.documents(provider.scopes()[0]))
    stopped = [value for value in safe if isinstance(value, SkippedDocument)]
    assert len(stopped) == 1 and stopped[0].abort_inventory
    assert stopped[0].code == "source_permission_denied"
    assert stopped[0].path == "nested"
    assert not any(isinstance(value, Document) for value in safe)
    rendered = repr(safe)
    assert "PRIVATE_OS_STRING" not in rendered and str(root) not in rendered
    seen["unsafe"] = True
    omitted = list(provider.documents(provider.scopes()[0]))
    hidden = [value for value in omitted if isinstance(value, SkippedDocument)]
    assert len(hidden) == 1 and hidden[0].path == ""
    assert hidden[0].code == "source_permission_denied" and hidden[0].abort_inventory
    receipt = hidden[0].report()
    assert receipt == {"error_code": "source_permission_denied"}
    rendered = repr(omitted)
    assert "PRIVATE_OS_STRING" not in rendered and str(outside) not in rendered


def test_unencodable_directory_name_keeps_the_category_and_a_real_path_keeps_its_hash(
    tmp_path, monkeypatch
):
    """A surrogate onerror name is omitted. A safe relative path keeps its hash."""
    import errno
    from pathlib import Path

    from mnemion.connectors import providers
    from mnemion.connectors.protocol import SkippedDocument
    from mnemion.connectors.source_files import relative_evidence
    from mnemion.service.connector_models import SourceFileError

    root = tmp_path / "vault"
    root.mkdir()
    (root / "a-kept.md").write_text("Permitted source")
    surrogate = "bad-\udcff"

    def walk(top, onerror=None, followlinks=False):
        if onerror is not None:
            onerror(PermissionError(errno.EACCES, "PRIVATE_OS_STRING", str(Path(top) / surrogate)))
        return
        yield

    monkeypatch.setattr(providers.os, "walk", walk)
    provider = FilesystemProvider(FilesystemConfig(path=root, **published()))
    stopped = [
        value
        for value in provider.documents(provider.scopes()[0])
        if isinstance(value, SkippedDocument)
    ]
    assert len(stopped) == 1 and stopped[0].abort_inventory and stopped[0].path == ""
    assert stopped[0].code == "source_permission_denied"
    assert stopped[0].report() == {"error_code": "source_permission_denied"}
    rendered = repr(stopped)
    assert "PRIVATE_OS_STRING" not in rendered and "\\udcff" not in rendered
    assert relative_evidence(surrogate) == {}
    expected = hashlib.sha256(b"nested/ok.md").hexdigest()
    assert relative_evidence("nested/ok.md") == {"path": "nested/ok.md", "path_sha256": expected}
    assert (
        SkippedDocument("nested/ok.md", "source_permission_denied", abort_inventory=True).report()[
            "path_sha256"
        ]
        == expected
    )
    assert SourceFileError(error_code="source_permission_denied").model_dump(exclude_none=True) == {
        "error_code": "source_permission_denied"
    }
    SourceFileError(
        error_code="source_permission_denied", path="nested/ok.md", path_sha256=expected
    )
    with pytest.raises(ValidationError):
        SourceFileError(error_code="source_permission_denied", path="nested/ok.md")
    with pytest.raises(ValidationError):
        SourceFileError(error_code="source_permission_denied", path_sha256=expected)
    with pytest.raises(ValidationError):
        SourceFileError(
            error_code="source_permission_denied", path="/etc/passwd", path_sha256=expected
        )
    with pytest.raises(ValidationError):
        SourceFileError(
            error_code="source_permission_denied", path="../secret.md", path_sha256=expected
        )


def test_journal_access_stop_keeps_its_receipt_and_projects_nothing():
    """Not run on 1 November 2026. An access stop must not become a partial journal."""
    from uuid import uuid4

    from mnemion.connectors.journal_projection import project_documents
    from mnemion.connectors.protocol import Document, SkippedDocument
    from mnemion.journal.format import JournalEntry, JournalError

    tenant, space, writer = uuid4(), uuid4(), uuid4()
    entry = JournalEntry(
        id=uuid4(),
        ts="2026-10-01T10:20:30Z",
        tenant_id=tenant,
        space_id=space,
        memory_id=uuid4(),
        version=1,
        writer=writer,
        subject="Kept",
        text="Postgres journal kept",
    )
    journal = Document(
        entry.relative_path,
        entry.digest,
        entry.relative_path,
        entry.line().decode(),
        metadata={"path": entry.relative_path},
    )
    stop = SkippedDocument("catalog.json", "source_permission_denied", abort_inventory=True)
    projected = list(project_documents([journal, stop]))
    assert projected == [stop]
    assert "Postgres journal kept" not in repr(projected)
    with pytest.raises(JournalError) as malformed:
        list(project_documents([SkippedDocument("catalog.json", "source_is_not_utf8_text")]))
    assert malformed.value.code == "journal_inventory_unreadable"
    bad_catalog = Document(
        "catalog.json",
        "1",
        "catalog.json",
        '{"format":"mnemion-memory-journal-catalog"}\n',
        metadata={"path": "catalog.json"},
    )
    with pytest.raises(JournalError) as invalid:
        list(project_documents([bad_catalog]))
    assert invalid.value.code == "invalid_journal_catalog"


def test_file_replaced_after_checks_cannot_escape_selected_vault(tmp_path, monkeypatch):
    from mnemion.connectors import source_files

    root = tmp_path / "selected"
    root.mkdir()
    source = root / "note.md"
    source.write_text("Permitted source")
    outside = tmp_path / "outside.md"
    outside.write_text("OUTSIDE_SELECTED_SOURCE")
    probe = tmp_path / "probe-link"
    try:
        probe.symlink_to(outside)
        probe.unlink()
    except OSError:
        pytest.skip("Creating test symlinks requires Windows developer mode or privilege")
    if os.name == "nt":
        original = source_files._windows_open_unfollowed

        def replace(path, relative):
            if os.path.basename(os.fspath(path)) == "note.md":
                source.unlink()
                source.symlink_to(outside)
            return original(path, relative)

        monkeypatch.setattr(source_files, "_windows_open_unfollowed", replace)
    else:
        original_open = source_files.os.open

        def replace(path, flags, *args, **kwargs):
            if os.fspath(path) in {"note.md", str(source)}:
                source.unlink()
                source.symlink_to(outside)
            return original_open(path, flags, *args, **kwargs)

        # Keep the openat capability set intact while replacing the call itself.
        monkeypatch.setattr(source_files.os, "supports_dir_fd", {*os.supports_dir_fd, replace})
        monkeypatch.setattr(source_files.os, "open", replace)
    provider = FilesystemProvider(FilesystemConfig(path=root, **published()))
    from mnemion.connectors.protocol import Document, SkippedDocument

    results = list(provider.documents(provider.scopes()[0]))
    assert not any(
        isinstance(value, Document) and "OUTSIDE_SELECTED_SOURCE" in value.text for value in results
    )
    stopped = [value for value in results if isinstance(value, SkippedDocument)]
    assert stopped and stopped[0].abort_inventory and stopped[0].path == "note.md"
    assert stopped[0].code in {
        "source_link_or_handle_changed",
        "source_outside_selected_root",
        "source_is_not_regular_file",
    }
    assert "OUTSIDE_SELECTED_SOURCE" not in repr(results)


def test_real_git_snapshot_ignores_uncommitted_work_and_never_executes_hooks(tmp_path):
    if not shutil.which("git"):
        pytest.skip("Install Git to exercise native Git source import")
    root = tmp_path / "Git café"
    root.mkdir()

    def git(*args):
        return subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "core.hooksPath=" + str(tmp_path / "no-hooks"),
                "-C",
                str(root),
                *args,
            ],
            check=True,
            capture_output=True,
        ).stdout

    git("init")
    path = root / "Decision.md"
    path.write_text("Committed decision")
    git("add", ".")
    git("commit", "-m", "Fixture")
    path.write_text("Uncommitted personal edit")
    provider = GitProvider(GitConfig(path=root, **published()))
    scope = provider.scopes()[0]
    docs = [doc for doc in provider.documents(scope) if doc]
    assert len(docs) == 1 and docs[0].text == "Committed decision"
    assert docs[0].metadata["git_commit"] == git("rev-parse", "HEAD").decode().strip()
    assert (
        docs[0].metadata["source_modified_at"]
        == git("log", "-1", "--format=%cI", "--", "Decision.md").decode().strip()
    )
    assert provider.access(scope).members == ["user:alice"]


def test_git_document_revisions_survive_unrelated_commits_merges_and_rollback(tmp_path):
    commit_sequence = 0

    def git(*args):
        nonlocal commit_sequence
        environment = os.environ.copy()
        if args[0] in {"commit", "merge"}:
            commit_sequence += 1
            timestamp = f"{1790000000 + commit_sequence} +0000"
            environment.update(GIT_AUTHOR_DATE=timestamp, GIT_COMMITTER_DATE=timestamp)
        return (
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "-c",
                    "core.hooksPath=" + str(tmp_path / "no-hooks"),
                    "-C",
                    str(tmp_path),
                    *args,
                ],
                check=True,
                capture_output=True,
                timeout=10,
                env=environment,
            )
            .stdout.decode()
            .strip()
        )

    def snapshot(ref="HEAD"):
        provider = GitProvider(
            GitConfig(
                path=tmp_path, ref=ref, web_url="https://example.invalid/team/memory", **published()
            )
        )
        return {doc.external_id: doc for doc in provider.documents(provider.scopes()[0]) if doc}

    git("init")
    for name in ("keep.md", "[draft].md", "d.md", "old.md"):
        (tmp_path / name).write_text(f"Original evidence in {name}")
    git("add", ".")
    git("commit", "-m", "Initial evidence")
    initial = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    before = snapshot()
    (tmp_path / "d.md").write_text("Updated d evidence")
    (tmp_path / "new.md").write_text("New evidence")
    git("mv", "old.md", "renamed.md")
    git("add", ".")
    git("commit", "-m", "Change selected paths")
    after = snapshot()
    assert set(after) == {"keep.md", "[draft].md", "d.md", "new.md", "renamed.md"}
    for name in ("keep.md", "[draft].md"):
        assert list(after[name].items()) == list(before[name].items())
        assert f"/blob/{initial}/" in after[name].uri
    assert after["d.md"].revision != before["d.md"].revision
    assert (
        after["d.md"].metadata["source_modified_at"]
        != after["[draft].md"].metadata["source_modified_at"]
    )
    assert (
        next(after["renamed.md"].items()).external_id != next(before["old.md"].items()).external_id
    )
    git("commit", "--allow-empty", "-m", "No source changes")
    assert snapshot() == after
    assert snapshot(initial) == before

    git("checkout", "-b", "fixture-side", initial)
    (tmp_path / "keep.md").write_text("Evidence changed on the side branch")
    git("add", "keep.md")
    git("commit", "-m", "Side branch evidence")
    git("checkout", branch)
    git("merge", "--no-ff", "fixture-side", "-m", "Merge evidence")
    merged = snapshot()
    assert merged["keep.md"].revision != after["keep.md"].revision
    assert merged["[draft].md"] == after["[draft].md"]
    assert merged["d.md"] == after["d.md"]
    for name, doc in merged.items():
        assert git("show", f"{doc.metadata['git_commit']}:{name}") == doc.text
        assert doc.metadata["source_modified_at"] == git(
            "--literal-pathspecs", "log", "-1", "--format=%cI", "--", name
        )


@pytest.mark.parametrize("reason", ["startup", "poll", "requested", "private-invalid-sentinel"])
@pytest.mark.parametrize("watch", [False, True])
def test_runner_reports_managed_scan_reason_but_plain_watch_starts_fresh(
    tmp_path, monkeypatch, capsys, reason, watch
):
    from types import SimpleNamespace
    from mnemion.connectors import runner

    monkeypatch.setenv(runner.SCAN_TRIGGER_ENV, reason)
    monkeypatch.setattr(
        runner, "read_config", lambda _: SimpleNamespace(poll_seconds=30, capture=None)
    )
    monkeypatch.setattr(runner, "sync", lambda *args, **kwargs: {"completed": True})

    def stop(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(runner, "wait_for_sync", stop)
    code = runner.main(
        ["--config", str(tmp_path / "fixture.json"), *(["--watch"] if watch else [])]
    )
    assert code == (130 if watch else 0)
    output = capsys.readouterr().out
    report = json.loads(output.splitlines()[-1])
    assert report["trigger"] == (
        "startup" if watch or reason == "private-invalid-sentinel" else reason
    )
    assert "private-invalid-sentinel" not in output


def test_rclone_uses_read_only_commands_and_checks_remote_hashes(tmp_path, monkeypatch):
    calls = []
    data = b"# A cloud note\n"
    entry = {
        "Path": "notes/one.md",
        "Size": len(data),
        "Hashes": {"sha256": hashlib.sha256(data).hexdigest()},
        "ID": "remote-one",
        "ModTime": "2026-01-01T00:00:00Z",
    }

    def run(args, **kwargs):
        calls.append(args)
        return json.dumps([entry]).encode() if "lsjson" in args else data

    monkeypatch.setattr("mnemion.connectors.providers.command", run)
    provider = RcloneProvider(
        RcloneConfig(
            remote="company:Shared vault", config_file=tmp_path / "private.conf", **published()
        )
    )
    docs = [doc for doc in provider.documents(provider.scopes()[0]) if doc]
    assert docs[0].text == data.decode()
    assert [call[3] for call in calls] == ["lsjson", "cat"]
    assert calls[-1][-1] == "company:Shared vault/notes/one.md"
    entry["Hashes"]["sha256"] = "0" * 64
    with pytest.raises(ProviderError, match="changed_during_read"):
        list(provider.documents(provider.scopes()[0]))


def test_slack_membership_pagination_threads_rate_limit_and_no_message_sends(tmp_path):
    token = tmp_path / "slack.token"
    token.write_text("fixture-token-a")
    requests = []
    waits = []
    limited = False

    def handler(request):
        nonlocal limited
        requests.append(request)
        name = request.url.path.split("/")[-1]
        assert request.method == "GET"
        if name == "auth.test":
            return httpx.Response(
                200, json={"ok": True, "team_id": "T123", "url": "https://fixture.slack.com/"}
            )
        if name == "conversations.info":
            return httpx.Response(
                200, json={"ok": True, "channel": {"id": "C123", "name": "project"}}
            )
        if name == "conversations.members":
            if not request.url.params.get("cursor"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "members": ["U123"],
                        "response_metadata": {"next_cursor": "members-next"},
                    },
                )
            return httpx.Response(200, json={"ok": True, "members": ["U456"]})
        if name == "conversations.history":
            if not limited:
                limited = True
                token.write_text("fixture-token-b")
                return httpx.Response(429, headers={"Retry-After": "1"})
            assert request.headers["Authorization"] == "Bearer fixture-token-b"
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "messages": [
                        {
                            "ts": "1700000000.000001",
                            "text": "Decision",
                            "user": "U123",
                            "reply_count": 1,
                        }
                    ],
                },
            )
        if name == "conversations.replies":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "messages": [
                        {"ts": "1700000000.000001", "text": "Decision", "user": "U123"},
                        {
                            "ts": "1700000000.000002",
                            "thread_ts": "1700000000.000001",
                            "text": "Supporting context",
                            "user": "U456",
                        },
                    ],
                },
            )
        raise AssertionError(name)

    provider = SlackProvider(
        SlackConfig(token=Token(file=token), team_id="T123", channels=["C123"]),
        transport=httpx.MockTransport(handler),
        sleep=waits.append,
    )
    scope = provider.scopes()[0]
    assert provider.access(scope).members == ["slack-user:U123", "slack-user:U456"]
    docs = [doc for doc in provider.documents(scope) if doc]
    assert len(docs) == 2 and docs[1].text == "Supporting context" and waits == [1]
    assert docs[1].uri == "https://fixture.slack.com/archives/C123/p1700000000000002"
    assert len({item.external_id for doc in docs for item in doc.items()}) == 2
    provider.close()


def test_slack_does_not_certify_truncated_or_repeated_history(monkeypatch):
    monkeypatch.setenv("SLACK_TEST_TOKEN", "fixture-only")
    provider = SlackProvider(
        SlackConfig(token=Token(env="SLACK_TEST_TOKEN"), team_id="T123", channels=["C123"]),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True, "messages": [], "has_more": True})
        ),
    )
    with pytest.raises(ProviderError, match="incomplete_pagination"):
        list(provider.pages("conversations.history", channel="C123"))
    provider.close()


def test_drive_file_permissions_export_and_shared_drive_flags(monkeypatch):
    monkeypatch.setenv("DRIVE_TEST_TOKEN", "fixture-only")
    requests = []
    file = {
        "id": "file-1",
        "name": "Project doc",
        "mimeType": "application/vnd.google-apps.document",
        "version": "7",
        "modifiedTime": "2026-01-01T00:00:00Z",
        "capabilities": {"canDownload": True},
    }

    def handler(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("/file-1/permissions"):
            if not request.url.params.get("pageToken"):
                return httpx.Response(
                    200,
                    json={
                        "nextPageToken": "acl-next",
                        "permissions": [{"id": "owner1", "type": "user", "role": "owner"}],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "permissions": [
                        {"id": "group1", "type": "group", "role": "reader"},
                        {"id": "anyone", "type": "anyone", "role": "reader"},
                        {
                            "id": "old",
                            "type": "user",
                            "role": "reader",
                            "expirationTime": "2020-01-01T00:00:00Z",
                        },
                        {"id": "person2", "type": "user", "role": "reader"},
                    ]
                },
            )
        if path.endswith("/file-1/export"):
            return httpx.Response(200, content="Décision: utiliser Postgres".encode())
        if path.endswith("/file-1"):
            return httpx.Response(200, json=file)
        raise AssertionError(path)

    provider = DriveProvider(
        DriveConfig(token=Token(env="DRIVE_TEST_TOKEN"), file_ids=["file-1"]),
        transport=httpx.MockTransport(handler),
    )
    scope = provider.scopes()[0]
    assert provider.access(scope).members == ["google-user:owner1", "google-user:person2"]
    doc = list(provider.documents(scope))[0]
    assert doc.text == "Décision: utiliser Postgres" and doc.metadata["provider_version"] == "7"
    assert all(
        r.url.params.get("supportsAllDrives") == "true"
        for r in requests
        if not r.url.path.endswith("/export")
    )
    provider.close()


def test_spreadsheets_preserve_all_sheets_and_reject_entity_expansion():
    def archive(unsafe=False):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as z:
            z.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="First" r:id="one"/><sheet name="Second" r:id="two"/></sheets></workbook>',
            )
            z.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="one" Target="worksheets/sheet1.xml"/><Relationship Id="two" Target="worksheets/sheet2.xml"/></Relationships>',
            )
            for i, value in enumerate(("Billing", "Garden"), 1):
                z.writestr(
                    f"xl/worksheets/sheet{i}.xml",
                    ("<!DOCTYPE boom>" if unsafe else "")
                    + f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>{value}</t></is></c></row></sheetData></worksheet>',
                )
        return output.getvalue()

    result = spreadsheet(archive())
    assert "# Sheet: First" in result and "# Sheet: Second" in result
    assert "Billing" in result and "Garden" in result
    with pytest.raises(ProviderError, match="entities_not_allowed"):
        spreadsheet(archive(True))


def test_configuration_rejects_unsafe_urls_and_requires_explicit_publication(tmp_path):
    with pytest.raises(ValidationError):
        FilesystemConfig(path=tmp_path, scope_id="vault", name="Vault", members=[])
    body = {
        "service_url": "http://company.example",
        "connector_id": str(uuid4()),
        "service_token": {"env": "MNEMION_TOKEN"},
        "provider": {"type": "filesystem", "path": "notes", **published()},
    }
    with pytest.raises(ValidationError):
        ConnectorConfig.model_validate(body)
    body["service_url"] = "https://memory.example.invalid"
    body["service_token"] = {"file": "private/token"}
    path = tmp_path / "connector.json"
    path.write_text(json.dumps(body))
    config = read_config(path)
    assert config.service_token.file == tmp_path / "private/token"
    assert config.provider.path == tmp_path / "notes"
    with pytest.raises(ValidationError):
        GitConfig(
            path=tmp_path, remote="https://user:secret@example.invalid/repo.git", **published()
        )
