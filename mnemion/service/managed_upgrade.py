"""Explicit, journaled schema upgrades for an already adopted managed host."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import psycopg

from . import service_updates as updates
from . import update_state as state_io
from .update_manifest import ManifestError, version_tuple

GUIDE = "https://github.com/Perseusxrltd/mnemion/blob/main/docs/service/managed-upgrades.md"
JOURNAL = "upgrade-journal.json"


def pending_update(active: dict, release) -> dict | None:
    if not release.is_newer_than(active["version"]):
        return None
    reasons = []
    if dict(release.migrations) != active["migrations"]:
        reasons.append("schema_changed")
    if not updates.compatible_version(active["version"], release.version):
        reasons.append("version_series_changed")
    return {
        "available_version": release.version,
        "operator_required": bool(reasons),
        "upgrade_reasons": reasons,
        "upgrade_guide": GUIDE,
    }


def upgrade_status(root: Path) -> dict | None:
    path = root / JOURNAL
    if not path.exists():
        return None
    value = state_io.read(path)
    return {
        "version": value["candidate"]["version"],
        "phase": value["phase"],
        "recovery_required": True,
        "backup": value["backup"],
        "upgrade_guide": GUIDE,
    }


def extension(previous: dict[str, str], target: dict[str, str]) -> list[str]:
    old, new = sorted(previous), sorted(target)
    if (
        not old
        or new[: len(old)] != old
        or any(target.get(name) != digest for name, digest in previous.items())
    ):
        raise ManifestError(
            "The target must preserve every applied migration and append new migrations in order"
        )
    return new[len(old) :]


def _owner(state: Path, root: Path) -> str:
    owner = state_io.read(root / "owner.json")["admin_database_url"]
    if any(
        updates._target(owner) != updates._target(state_io.read(state / filename)[field])
        for filename, field in (
            ("api.json", "database_url"),
            ("worker.json", "worker_database_url"),
        )
    ):
        raise ManifestError("Upgrade and runtime credentials must name the same database")
    return owner


def _schema(state: Path, root: Path) -> dict[str, str]:
    with psycopg.connect(_owner(state, root), connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout='10s'")
        return dict(conn.execute("SELECT name, sha256 FROM mnemion.schema_migrations").fetchall())


def plan(state: Path) -> dict:
    state, root, _ = updates._root(state)
    with state_io.lock(root):
        if (root / JOURNAL).exists():
            return {"status": "recovery_required", **upgrade_status(root)}
        result = updates._check(root)
        if result["status"] != "available":
            return result
        release = updates._release(root)
        active = updates.resolved_runtime(state)
        migrations = extension(active["migrations"], dict(release.migrations))
        same_major = version_tuple(active["version"])[0] == version_tuple(release.version)[0]
        return {
            **result,
            "status": "planned" if same_major else "unsupported_major_upgrade",
            "source_commit": release.commit,
            "migrations": migrations,
            "backup_before_changes": True,
            "model_generations_must_match": True,
            "service_interruption": True,
            "database_rollback_automatic": False,
            "command": [
                "mnemion-service",
                "updates",
                "upgrade",
                "--state-dir",
                str(state),
                "--version",
                release.version,
                "--allow-migration",
            ]
            if same_major
            else None,
            "upgrade_guide": GUIDE,
        }


def _phase(root: Path, journal: dict, phase: str) -> None:
    journal["phase"] = phase
    state_io.write(root / JOURNAL, journal)


def migrate_journal(state: Path) -> dict:
    """Executed by the verified candidate; its entire DDL change is one transaction."""
    from ..version import __version__
    from .db import migrate

    state, root, _ = updates._root(state)
    journal = state_io.read(root / JOURNAL)
    candidate = updates.resolved_runtime(state, runtime=journal["candidate"])
    if (
        journal["phase"] != "migrating"
        or candidate["version"] != __version__
        or candidate["migrations"] != state_io.local_migrations()
    ):
        raise ManifestError("The migration process does not match the reviewed candidate")
    extension(journal["previous"]["migrations"], candidate["migrations"])
    return {"applied": migrate(_owner(state, root), expected=journal["previous"]["migrations"])}


def _migrate(state: Path, root: Path, candidate: dict) -> None:
    updates._command(
        [candidate["python"], "-I", "-m", "mnemion.service.managed_upgrade", str(state)],
        cwd=Path(candidate["directory"]),
        environment=updates._environment(),
        log=root / "logs/migration.log",
        timeout=900,
    )


def _validate(previous: dict, candidate: dict) -> list[str]:
    if (
        version_tuple(candidate["version"]) <= version_tuple(previous["version"])
        or version_tuple(candidate["version"])[0] != version_tuple(previous["version"])[0]
    ):
        raise ManifestError(
            "An operator upgrade requires a newer release in the same major version"
        )
    if candidate["generations"] != previous["generations"]:
        raise ManifestError("Changed model generations need a separately planned reindex")
    return extension(previous["migrations"], candidate["migrations"])


def _resume_failure(state: Path, root: Path, journal: dict) -> None:
    """Roll back only an uncommitted migration; never discard accepted database writes."""
    updates._processes(state, start=False)
    current = _schema(state, root)
    if current == journal["previous"]["migrations"]:
        updates.resolved_runtime(state, runtime=journal["previous"])
        state_io.write(root / "active.json", journal["previous"])
        updates._processes(state, start=True, service_only=True)
        state_io.record(
            root,
            "upgrade_rolled_back_before_migration",
            version=journal["candidate"]["version"],
            database_restored=False,
        )
        (root / JOURNAL).unlink()
        updates._processes(state, start=True, updater_only=True)
        return
    _phase(root, journal, "recovery_required")
    state_io.record(
        root,
        "upgrade_recovery_required",
        version=journal["candidate"]["version"],
        database_restored=False,
    )


def upgrade(
    state: Path, *, version: str | None, allow_migration: bool = False, resume: bool = False
) -> dict:
    if not allow_migration or version is None:
        raise ManifestError("Review updates plan, then supply --version and --allow-migration")
    version_tuple(version)
    state, root, settings = updates._root(state)
    with state_io.lock(root):
        path = root / JOURNAL
        if path.exists():
            if not resume:
                raise ManifestError("An interrupted upgrade exists; review status and use --resume")
            journal = state_io.read(path)
            if journal["candidate"]["version"] != version:
                raise ManifestError("Resume must name the version in the existing upgrade journal")
            previous = updates.resolved_runtime(state, runtime=journal["previous"])
            candidate = updates.resolved_runtime(state, runtime=journal["candidate"])
            migrations = _validate(previous, candidate)
            from ..archives import verified_archive
            from .recovery import BACKUP_FORMAT

            if Path(journal["backup"]).name != journal["backup"]:
                raise ManifestError("Invalid upgrade backup path")
            with verified_archive(root / "backups" / journal["backup"], BACKUP_FORMAT):
                pass
        else:
            if resume:
                raise ManifestError("There is no interrupted upgrade to resume")
            updates._recover(state, root)
            result = updates._check(root)
            if result.get("available_version") != version:
                raise ManifestError(
                    "The signed available version changed; review a fresh upgrade plan"
                )
            release = updates._release(root)
            previous = updates.resolved_runtime(state)
            if version_tuple(release.version)[0] != version_tuple(previous["version"])[0]:
                raise ManifestError("Major upgrades require a separate migration procedure")
            extension(previous["migrations"], dict(release.migrations))
            updates._stage(root, settings)
            candidate = updates.resolved_runtime(
                state, runtime=state_io.read(updates._slot(root, release) / "ready.json")["runtime"]
            )
            migrations = _validate(previous, candidate)
            if not updates.supervision.status(state)["running"]:
                raise ManifestError("Start the managed supervisor before upgrading")
            if updates._models(candidate, settings, root) != updates._models(
                previous, settings, root
            ):
                raise ManifestError(
                    "Live model configuration changed; resolve it before this upgrade"
                )
            backup = updates._backup(root, settings, previous, release, allow_migration=True)
            journal = {
                "format": 1,
                "phase": "prepared",
                "previous": previous,
                "candidate": candidate,
                "backup": backup,
                "at": state_io.timestamp(),
            }
            state_io.write(path, journal, replace=False)
        # Recheck settings and immutable installed bytes before any process change.
        if resume and updates._models(candidate, settings, root) != updates._models(
            previous, settings, root
        ):
            raise ManifestError("Live model configuration changed; resolve it before this upgrade")
        try:
            updates._processes(state, start=False, updater_only=True)
            updates._processes(state, start=False)
            current = _schema(state, root)
            if current == previous["migrations"]:
                _phase(root, journal, "migrating")
                if migrations:
                    _migrate(state, root, candidate)
                if _schema(state, root) != candidate["migrations"]:
                    raise ManifestError("The migration did not produce the signed target schema")
            elif current != candidate["migrations"]:
                raise ManifestError("Database schema differs from both recorded upgrade endpoints")
            _phase(root, journal, "schema_committed")
            state_io.write(root / "active.json", candidate)
            _phase(root, journal, "starting")
            updates._processes(state, start=True, service_only=True)
        except Exception:
            try:
                _resume_failure(state, root, journal)
            except Exception:
                _phase(root, journal, "recovery_required")
            raise ManifestError(
                "The upgrade did not finish. Inspect updates status and the private logs; use --resume if recovery is pending. No database backup was restored."
            ) from None
        state_io.write(root / "previous.json", previous)
        result = {
            "status": "upgraded",
            "from_version": previous["version"],
            "version": candidate["version"],
            "migrations": migrations,
            "backup": journal["backup"],
            "database_restored": False,
        }
        state_io.write(root / "last-upgrade.json", {**result, "at": state_io.timestamp()})
        state_io.record(
            root,
            "schema_upgraded",
            **{key: value for key, value in result.items() if key != "status"},
        )
        path.unlink()
    try:
        updates._processes(state, start=True, updater_only=True)
    except Exception:
        state_io.record(root, "updater_restart_failed", version=candidate["version"])
        raise ManifestError(
            "The service upgraded; restart its updater through Supervisor"
        ) from None
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(migrate_journal(Path(sys.argv[1]))))
    except Exception:
        print(
            json.dumps(
                {"error": "The guarded migration failed; no partial transaction was committed."}
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
