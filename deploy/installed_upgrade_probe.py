"""Exercise a real installed schema upgrade and restore on disposable native CI.

Uses the packaged setup/reopen UI with an isolated profile. This is an operator
installation and migration gate, separate from the unmodified public-feed test.
Never run against a user's profile or an existing machine installation.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import traceback
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from uuid import uuid4

from deploy.native_resources import verify, verify_component
from deploy.public_update_probe import asar_json, child_environment, installer_name, run
from deploy.published_release import NoRedirects, version

REPOSITORY = "Perseusxrltd/mnemion"


def gh(*arguments: str) -> str:
    result = subprocess.run(
        ["gh", *arguments], capture_output=True, text=True, timeout=300, check=False
    )
    if result.returncode or len(result.stdout) > 16 * 1024**2:
        raise RuntimeError("Release retrieval failed; inspect private runner diagnostics")
    return result.stdout


def inventory(release: dict, checksums: bytes, *, tag: str, commit: str | None) -> dict:
    version(tag)
    if release.get("tag_name") != tag or release.get("prerelease") is not False:
        raise ValueError("The selected stable release has a different identity")
    if commit is None:
        if release.get("draft") is not False or not release.get("published_at"):
            raise ValueError("The previous installer must already be public")
    elif not re.fullmatch(r"[a-f0-9]{40}", commit) or release.get("target_commitish") != commit:
        raise ValueError("The candidate release differs from its pinned source commit")
    assets = {}
    for row in release.get("assets", []):
        name = row.get("name", "")
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}", name)
            or name in assets
            or row.get("state") != "uploaded"
            or type(row.get("size")) is not int
            or not 0 < row["size"] <= 2 * 1024**3
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", row.get("digest", ""))
            or row.get("browser_download_url")
            != f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
        ):
            raise ValueError("Invalid release asset identity")
        assets[name] = row
    checksum = assets.get("SHA256SUMS.txt", {})
    if (
        not 0 < len(checksums) <= 1024**2
        or checksum.get("size") != len(checksums)
        or checksum.get("digest") != "sha256:" + hashlib.sha256(checksums).hexdigest()
    ):
        raise ValueError("Release checksums differ from GitHub's asset digest")
    listed = {}
    for line in checksums.decode("utf-8").splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]{0,254})", line)
        if not match or match[2] in listed:
            raise ValueError("Malformed or duplicated checksum entry")
        listed[match[2]] = "sha256:" + match[1]
    if set(listed) != set(assets) - {"SHA256SUMS.txt"} or any(
        assets[name]["digest"] != digest for name, digest in listed.items()
    ):
        raise ValueError("The complete asset and checksum inventories disagree")
    return assets


def release_files(tag: str, system: str, arch: str, root: Path, *, commit=None) -> Path:
    releases = json.loads(gh("api", f"repos/{REPOSITORY}/releases?per_page=100"))
    release = next(row for row in releases if row.get("tag_name") == tag)
    root.mkdir(mode=0o700)
    gh(
        "release",
        "download",
        tag,
        "--repo",
        REPOSITORY,
        "--dir",
        str(root),
        "--pattern",
        "SHA256SUMS.txt",
    )
    assets = inventory(release, (root / "SHA256SUMS.txt").read_bytes(), tag=tag, commit=commit)
    names = [installer_name(tag, system, arch)]
    if commit:
        names.append("service-update.json")
    for name in names:
        asset = assets[name]
        gh("release", "download", tag, "--repo", REPOSITORY, "--dir", str(root), "--pattern", name)
        path = root / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (
            path.is_symlink()
            or path.stat().st_size != asset["size"]
            or asset["digest"] != "sha256:" + digest
        ):
            raise ValueError("Downloaded installer differs from its complete release inventory")
    if commit:
        from mnemion.service.update_manifest import verify_manifest
        from mnemion.service.update_trust import SERVICE_UPDATE_PUBLIC_KEY

        signed = verify_manifest(
            (root / "service-update.json").read_bytes(), SERVICE_UPDATE_PUBLIC_KEY
        )
        if signed.version != tag[1:] or signed.commit != commit:
            raise ValueError("The production signing key did not authenticate this candidate")
    return root / names[0]


class InstalledUpgrade:
    def __init__(self, args):
        self.args = args
        self.root = args.output.resolve()
        runner = Path(os.environ["RUNNER_TEMP"]).resolve()
        if self.root == runner or not self.root.is_relative_to(runner) or self.root.exists():
            raise ValueError(
                "Use a new private directory under the disposable runner temporary folder"
            )
        self.root.mkdir(mode=0o700)
        self.installed = self.root / "Applications Équipe with spaces"
        self.profile = self.root / "Private profile"
        self.workspace = self.profile / "mnemion-local-workspace"
        self.probe = self.root / "hosting-probe.json"
        self.smoke = self.root / "smoke.json"
        self.quit = self.root / "quit-request"
        self.environment = child_environment()
        self.child = None
        self.log = None
        self.executable = None
        self.resources = None
        self.stage = "download"

    def install(self, source: Path, tag: str):
        system = self.args.platform
        if system == "windows":
            self.installed.mkdir(exist_ok=True)
            env = {
                **self.environment,
                "MNEMION_PROBE_INSTALLER": str(source),
                "MNEMION_PROBE_DEST": str(self.installed),
            }
            run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    '$ErrorActionPreference="Stop"; $p=Start-Process -FilePath $env:MNEMION_PROBE_INSTALLER '
                    '-ArgumentList @("/S","/currentuser",("/D="+$env:MNEMION_PROBE_DEST)) '
                    "-PassThru -Wait; exit $p.ExitCode",
                ],
                env=env,
                timeout=420,
            )
            self.executable = self.installed / "Mnemion Studio.exe"
            self.resources = self.installed / "resources"
        else:
            if self.installed.exists():
                # Only the drained application bundle is replaced; profile and
                # database stay at their original, separate private locations.
                self.installed.rename(self.root / "previous-installed-application")
            self.installed.mkdir()
            if system == "macos":
                volume = self.root / "installer-volume"
                run(
                    ["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", volume, source],
                    env=self.environment,
                )
                bundle = self.installed / "Mnemion Studio.app"
                try:
                    run(["ditto", volume / bundle.name, bundle], env=self.environment)
                finally:
                    run(["hdiutil", "detach", volume], env=self.environment)
                run(["codesign", "--verify", "--deep", "--strict", bundle], env=self.environment)
                self.executable = bundle / "Contents/MacOS/Mnemion Studio"
                self.resources = bundle / "Contents/Resources"
            else:
                target = self.installed / source.name
                shutil.copyfile(source, target)
                target.chmod(0o755)
                result = subprocess.run(
                    [str(target), "--appimage-extract"],
                    cwd=self.installed,
                    env=self.environment,
                    capture_output=True,
                    timeout=180,
                )
                if result.returncode:
                    raise RuntimeError("The portable AppImage could not be extracted")
                self.executable = self.installed / "squashfs-root/AppRun"
                self.resources = self.installed / "squashfs-root/resources"
        if asar_json(self.resources / "app.asar")["version"] != tag[1:]:
            raise ValueError("The installed app has the wrong version")
        if tag == self.args.to_tag:
            verify(self.resources, system, self.args.arch, tag[1:])
        else:
            backend_arch = "x64" if system == "windows" else self.args.arch
            engine = verify_component(self.resources / "engine", "service", system, backend_arch)
            verify_component(self.resources / "postgresql", "postgresql", system, backend_arch)
            if engine["version"] != tag[1:]:
                raise ValueError("The previous packaged engine has a different version")

    def launch(self, config):
        self.smoke.unlink(missing_ok=True)
        self.quit.unlink(missing_ok=True)
        self.probe.write_text(json.dumps(config), encoding="utf-8")
        self.log = (self.root / (self.stage + ".private.log")).open("wb")
        environment = {
            **self.environment,
            "MNEMION_STUDIO_USER_DATA": str(self.profile),
            "MNEMION_STUDIO_SMOKE_FILE": str(self.smoke),
            "MNEMION_STUDIO_HOSTING_PROBE": str(self.probe),
            "MNEMION_AUTO_UPDATE": "0",
            "MNEMION_START_AT_LOGIN": "0",
        }
        self.child = subprocess.Popen(
            [str(self.executable)],
            cwd=self.installed,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
        )
        deadline = time.monotonic() + 720
        while time.monotonic() < deadline:
            if self.child.poll() is not None:
                raise RuntimeError("The installed app exited before UI acceptance")
            if self.smoke.is_file() and self.smoke.stat().st_size <= 128 * 1024:
                try:
                    result = json.loads(self.smoke.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    time.sleep(0.2)
                    continue
                if result.get("stage") == "hosting-ready":
                    return result["hosting"]
                if result.get("stage") in {
                    "startup-error",
                    "uncaught-exception",
                    "unhandled-rejection",
                    "backend-exit",
                }:
                    raise RuntimeError(
                        "The installed UI reported a failure; details remain private"
                    )
            time.sleep(0.2)
        raise TimeoutError("Installed UI acceptance timed out")

    def stop(self):
        if self.child is None:
            return
        if self.child.poll() is None:
            self.quit.write_text("quit\n", encoding="ascii")
            self.child.wait(timeout=120)
        if self.child.returncode != 0 or (self.workspace / "database/postmaster.pid").exists():
            raise RuntimeError("The installed app did not drain its real database")
        self.child = None
        self.log.close()
        self.log = None

    def database(self):
        from mnemion import local_state
        from mnemion.local_database import LocalDatabase

        return LocalDatabase(
            self.workspace,
            self.resources / "postgresql",
            local_state.read(self.workspace / "configuration.json"),
            local_state.read(self.workspace / "credentials.json"),
        )

    def snapshot(self):
        import psycopg
        from psycopg import sql

        database = self.database()
        with psycopg.connect(database.dsn()) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            result = {
                "schema": dict(
                    connection.execute("SELECT name,sha256 FROM mnemion.schema_migrations")
                )
            }
            for table in (
                "tenants",
                "principals",
                "api_keys",
                "space_grants",
                "memories",
                "memory_revisions",
            ):
                rows = connection.execute(
                    sql.SQL(
                        'SELECT to_jsonb(t)::text FROM mnemion.{} t ORDER BY to_jsonb(t)::text COLLATE "C"'
                    ).format(sql.Identifier(table))
                ).fetchall()
                result[table] = hashlib.sha256(
                    "\n".join(row[0] for row in rows).encode()
                ).hexdigest()
        return result

    def request(self, endpoint, key, method, path, body=None, *, expected=200):
        address = urlsplit(endpoint)
        if (
            address.scheme != "http"
            or address.hostname != "127.0.0.1"
            or address.username
            or address.password
            or address.path
            or not path.startswith("/v1/")
        ):
            raise ValueError("The installed test client can address only its loopback workspace")
        headers = {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Idempotency-Key": uuid4().hex,
        }
        request = Request(
            endpoint + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers=headers,
        )
        try:
            response = build_opener(NoRedirects()).open(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                raise RuntimeError("An isolated installed-service request had an unexpected status")
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("The isolated service response exceeded its bound")
            return json.loads(raw)

    def await_operation(self, endpoint, key, operation):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            value = self.request(endpoint, key, "GET", "/v1/operations/" + operation)
            if value["state"] in {"ready", "deleted"}:
                return
            if value["state"] == "failed":
                raise RuntimeError("An isolated indexing or deletion operation failed")
            time.sleep(0.25)
        raise TimeoutError("The isolated operation did not complete")

    def exercise(self):
        from mnemion import __version__, local_state
        from mnemion.archives import verified_archive
        from mnemion.service.recovery import BACKUP_FORMAT, export_ledger, restore_backup
        from mnemion.service.update_state import local_migrations
        from mnemion.service.db import Database
        from mnemion.service.errors import ServiceError
        import psycopg
        from psycopg import sql

        if __version__ != self.args.to_tag[1:]:
            raise ValueError("The verification source must match the candidate application")
        previous = release_files(
            self.args.from_tag, self.args.platform, self.args.arch, self.root / "previous"
        )
        candidate = release_files(
            self.args.to_tag,
            self.args.platform,
            self.args.arch,
            self.root / "candidate",
            commit=self.args.commit,
        )
        for name in ("GH_TOKEN", "GITHUB_TOKEN"):
            os.environ.pop(name, None)
        self.stage = "previous-install"
        self.install(previous, self.args.from_tag)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.stage = "previous-ui"
        first = self.launch(
            {
                "phase": "create",
                "port": port,
                "emulated": self.args.platform == "windows" and self.args.arch == "arm64",
            }
        )
        if not first["actualSetupControls"] or not first["realModelInference"]:
            raise ValueError("The previous installed UI did not use its actual setup and model")
        credentials = local_state.read(self.workspace / "credentials.json")
        credential_hash = hashlib.sha256(
            (self.workspace / "credentials.json").read_bytes()
        ).hexdigest()
        endpoint, owner = first["endpoint"], credentials["api_key"]
        author = self.request(
            endpoint,
            owner,
            "POST",
            "/v1/principals",
            {"name": "Installed upgrade contributor", "kind": "application"},
            expected=201,
        )
        author_key = self.request(
            endpoint,
            owner,
            "POST",
            "/v1/principals/" + author["id"] + "/keys",
            {"name": "Disposable contributor"},
            expected=201,
        )["api_key"]
        self.request(
            endpoint,
            owner,
            "PUT",
            "/v1/spaces/" + credentials["space_id"] + "/grants/" + author["id"],
            {"role": "contributor"},
        )
        saved = self.request(
            endpoint,
            author_key,
            "POST",
            "/v1/spaces/" + credentials["space_id"] + "/memories",
            {
                "content": "Disposable authored note for installed withdrawal and recovery validation."
            },
            expected=202,
        )
        self.await_operation(endpoint, author_key, saved["operation_id"])
        self.request(
            endpoint,
            author_key,
            "DELETE",
            "/v1/memories/" + saved["memory_id"] + "?expected_version=1",
            expected=403,
        )
        before = self.snapshot()
        self.stop()
        self.stage = "candidate-install"
        self.install(candidate, self.args.to_tag)
        self.stage = "candidate-ui"
        second = self.launch({"phase": "resume", "port": port, "memoryId": first["memoryId"]})
        if (
            not second["automaticReopen"]
            or second["tenantId"] != first["tenantId"]
            or second["endpoint"] != endpoint
        ):
            raise ValueError("The upgraded UI did not reopen its original workspace")
        if (
            hashlib.sha256((self.workspace / "credentials.json").read_bytes()).hexdigest()
            != credential_hash
        ):
            raise ValueError("The installed upgrade changed private workspace credentials")
        after = self.snapshot()
        if after["schema"] != local_migrations() or before["schema"] == after["schema"]:
            raise ValueError("This acceptance requires an actual checked schema migration")
        if any(after[key] != value for key, value in before.items() if key != "schema"):
            raise ValueError("The installed upgrade changed identities, grants or existing memory")
        detail = self.request(endpoint, author_key, "GET", "/v1/memories/" + saved["memory_id"])
        if detail.get("can_forget") is not True:
            raise ValueError("The migrated service did not authorize its existing contributor")
        deleted = self.request(
            endpoint,
            author_key,
            "DELETE",
            "/v1/memories/" + saved["memory_id"] + "?expected_version=1",
            expected=202,
        )
        self.await_operation(endpoint, author_key, deleted["operation_id"])
        backups = list((self.workspace / "backups").glob("before-" + __version__ + "-*.zip"))
        if len(backups) != 1:
            raise ValueError("Expected exactly one pre-migration recovery archive")
        backup = backups[0]
        with verified_archive(backup, BACKUP_FORMAT) as (manifest, _):
            if {row["name"]: row["sha256"] for row in manifest["schema"]} != before["schema"]:
                raise ValueError("The automatic backup was not captured before migration")
        self.stage = "isolated-backup-restore"
        database = self.database()
        ledger = self.workspace / "upgrade-recovery-ledger.json"
        recovery_keys = self.workspace / "upgrade-recovery-credentials.json"
        export_ledger(database.dsn(), ledger)
        restored_name = "mnemion_installed_recovery_" + uuid4().hex
        restore_backup(
            database.dsn(),
            backup,
            database_name=restored_name,
            deletion_ledger=ledger,
            credentials_output=recovery_keys,
            pg_bin=self.resources / "postgresql/bin",
        )
        restored = Database(database.dsn("api", database=restored_name))
        original = Database(database.dsn("api"))
        try:
            restored.open()
            original.open()
            for token in (owner, author_key):
                try:
                    restored.authenticate(token)
                except ServiceError as error:
                    if error.status != 401:
                        raise
                else:
                    raise ValueError("Restoration retained a copied API key")
                original.authenticate(token)
            restored.authenticate(local_state.read(recovery_keys)["api_key"])
            with psycopg.connect(database.dsn(database=restored_name)) as connection:
                row = connection.execute(
                    "SELECT deleted_at FROM mnemion.memories WHERE id=%s", (saved["memory_id"],)
                ).fetchone()
                if not row or row[0] is None:
                    raise ValueError("Restoration resurrected withdrawn memory")
                if connection.execute(
                    "SELECT count(*) FROM mnemion.memory_revisions WHERE memory_id=%s",
                    (saved["memory_id"],),
                ).fetchone()[0]:
                    raise ValueError("Restoration retained the withdrawn note's prose")
                if not connection.execute(
                    "SELECT 1 FROM mnemion.memories WHERE id=%s AND deleted_at IS NULL",
                    (first["memoryId"],),
                ).fetchone():
                    raise ValueError("Restoration lost the retained memory")
        finally:
            restored.close()
            original.close()
            with psycopg.connect(database.dsn(), autocommit=True) as connection:
                connection.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(restored_name))
                )
        self.stop()
        self.stage = "completed"
        with backup.open("rb") as stream:
            backup_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return {
            "passed": True,
            "at": datetime.now(timezone.utc).isoformat(),
            "platform": self.args.platform,
            "architecture": self.args.arch,
            "from": self.args.from_tag,
            "to": self.args.to_tag,
            "candidate_commit": self.args.commit,
            "real_previous_installer_and_model": True,
            "real_candidate_installer_and_reopen": True,
            "migrations_before": len(before["schema"]),
            "migrations_after": len(after["schema"]),
            "credentials_identities_grants_memories_preserved": True,
            "existing_contributor_withdrawal_and_purge": True,
            "automatic_pre_migration_backup_verified": True,
            "backup_sha256": backup_digest,
            "isolated_restore_with_current_ledger": True,
            "withdrawn_content_not_resurrected": True,
            "recovery_keys_rotated_original_keys_unchanged": True,
            "clean_database_shutdown": True,
            "scope": "Disposable installed schema migration; public automatic-update acceptance is separate.",
        }

    def cleanup(self):
        try:
            self.stop()
        except Exception:
            if self.child and self.child.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(self.child.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=30,
                    )
                else:
                    import signal

                    os.killpg(self.child.pid, signal.SIGKILL)
                self.child.wait(timeout=30)
        if self.log:
            self.log.close()
        if self.args.platform == "windows" and self.installed.is_dir():
            uninstallers = list(self.installed.glob("Uninstall *.exe"))
            if len(uninstallers) == 1:
                run([uninstallers[0], "/S"], env=self.environment, timeout=180)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-tag", required=True)
    parser.add_argument("--to-tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--platform", choices=["windows", "macos", "linux"], required=True)
    parser.add_argument("--arch", choices=["x64", "arm64"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        os.environ.get("CI") != "true"
        or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
    ):
        raise SystemExit(
            "Installed migration probes require this repository's disposable CI runners"
        )
    expected_os = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}[args.platform]
    if os.environ.get("RUNNER_OS") != expected_os or version(args.from_tag) >= version(args.to_tag):
        raise SystemExit("Invalid native runner or upgrade direction")
    if not re.fullmatch(r"[a-f0-9]{40}", args.commit):
        raise SystemExit("An exact candidate source commit is required")
    if args.platform == "windows":
        # Never let production NSIS discover and remove a pre-existing app.
        run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                '$entries=Get-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",'
                '"HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",'
                '"HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*" -ErrorAction SilentlyContinue; '
                'if ($entries | Where-Object { $_.DisplayName -eq "Mnemion Studio" }) { exit 1 }',
            ],
            env=child_environment(),
        )
    probe = InstalledUpgrade(args)
    try:
        result = probe.exercise()
    except Exception as error:
        result = {
            "passed": False,
            "stage": probe.stage,
            "error_type": type(error).__name__,
            "frames": [
                {"function": frame.name, "line": frame.lineno}
                for frame in traceback.extract_tb(error.__traceback__)[-4:]
            ],
            "platform": args.platform,
            "architecture": args.arch,
            "private_diagnostics": "Disposable runner only; no profile, keys or backup uploaded",
        }
    finally:
        probe.cleanup()
    (probe.root / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
