"""Bounded local numeric aggregates, with no network or operational-log access.

Call only from an owned producer outside a memory operation's critical path.
An observation carries the policy revision captured when it started, so an old
worker cannot restore discarded data after opt-out and subsequent re-enable.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import time

from . import policy
from .catalog import CATALOG, SURFACES, WORKFLOW_IDS, MeasurementError, describe, observation

# One bounded negative hint for the most recently disabled/exhausted store. It can
# only suppress optional work, never grant consent or skip a successful write's
# current-policy transaction. No connection, observations or result data survive.
_exhaustion: tuple[Path, int, int, float, tuple[int, ...]] | None = None


def _day() -> int:
    return int(time.time() // 86400)


def _file_version(root: Path) -> tuple[int, ...]:
    info = (root / policy.DATABASE_NAME).lstat()
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_size


def _exhausted(root: Path | None, scopes: tuple[int, ...], day: int) -> bool:
    global _exhaustion
    saved = _exhaustion
    if saved is None:
        return False
    root = root if root is not None else policy.default_directory()
    if root != saved[0]:
        return False
    now = time.monotonic()
    try:
        if (
            day != saved[1]
            or not saved[3] - 60 <= now < saved[3]
            or _file_version(root) != saved[4]
        ):
            _exhaustion = None
            return False
        return bool(scopes) and all(saved[2] & (1 << scope) for scope in scopes)
    except OSError:
        _exhaustion = None
        return False


def workflow_exhausted(root: Path | None, workflow: str, surface: str) -> bool:
    """Fast negative hint; an admitted workflow still reads current policy."""
    if _exhaustion is None:
        return False
    scope = WORKFLOW_IDS[workflow] * len(SURFACES) + SURFACES.index(surface)
    return _exhausted(root, (scope,), _day())


def remember_disabled(root: Path | None) -> None:
    """Only an observed explicit opt-out is cached; current reads still admit."""
    root = root if root is not None else policy.default_directory()
    _remember_exhaustion(root, [], _day(), disabled=True)


def _remember_exhaustion(root: Path, scopes: list[int], day: int, *, disabled=False) -> None:
    global _exhaustion
    if not scopes and not disabled:
        return
    try:
        bits = -1 if disabled else 0
        for scope in scopes:
            bits |= 1 << scope
        _exhaustion = root, day, bits, time.monotonic() + 60, _file_version(root)
    except OSError:
        _exhaustion = None


def _permitted(preference: dict, company: dict, revision: int, generation: str | None) -> bool:
    return (
        preference["revision"] == revision
        and policy.valid_generation(generation)
        and preference["store_generation"] == generation
        and preference["enabled"]
        and preference["disclosure_version"] == policy.DISCLOSURE_VERSION
        and company["enabled"]
        and bool(company["metric_groups"])
        and policy.COLLECTION_AVAILABLE
        and policy.COLLECTOR_URL is not None
    )


def _prune(connection: sqlite3.Connection, day: int, groups: list[str]) -> None:
    # Retaining only today/yesterday gives a conservative maximum age <48h;
    # no precise event timestamps are stored. Clock rollback drops future rows.
    connection.execute("DELETE FROM pending WHERE window_day < ? OR window_day > ?", (day - 1, day))
    connection.execute("DELETE FROM producer_budget WHERE window_day != ?", (day,))
    rows = connection.execute("SELECT cell FROM pending LIMIT 513").fetchall()
    if len(rows) > policy.MAX_PENDING:
        raise policy.PolicyError("telemetry_storage_unavailable")
    for (cell,) in rows:
        if describe(cell)["group"] not in groups:
            connection.execute("DELETE FROM pending WHERE cell=?", (cell,))


def record(
    root: Path | None,
    value: object,
    *,
    expected_revision: int,
    expected_generation: str | None = None,
    policy_path: Path | None = None,
) -> bool:
    """Best-effort, no-wait commit of one fixed observation."""
    return record_many(
        root,
        [value],
        expected_revision=expected_revision,
        expected_generation=expected_generation,
        policy_path=policy_path,
    )


def record_many(
    root: Path | None,
    values: object,
    *,
    expected_revision: int,
    expected_generation: str | None = None,
    policy_path: Path | None = None,
) -> bool:
    """Commit at most one workflow's pair under a single current-policy fence.

    False means suppressed/dropped/unavailable, not a product-operation failure.
    Validate and coarsen the entire pair before opening the private database.
    One connection/transaction avoids two durable commits per workflow. The
    unavailable collection gate still returns before any storage access.
    """
    if not policy.COLLECTION_AVAILABLE or policy.COLLECTOR_URL is None:
        return False
    if type(expected_revision) is not int or not 0 <= expected_revision < 2147483647:
        return False
    if not policy.valid_generation(expected_generation):
        return False
    try:
        if type(values) not in (list, tuple) or not 1 <= len(values) <= 2:
            return False
        observations = tuple(observation(value) for value in values)
        day = _day()
        if not 0 <= day <= 1000000:
            return False
        root = root if root is not None else policy.default_directory()
        if _exhausted(root, tuple(scope for scope, _ in observations), day):
            return False
        policy._root_safe(root)
        if not policy._file_safe(root / policy.DATABASE_NAME):
            return False
        with closing(policy._connect(root / policy.DATABASE_NAME)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            preference = policy._preferences(connection)
            # An old process cannot clear or add anything in the newer choice.
            if (
                preference["revision"] != expected_revision
                or preference["store_generation"] != expected_generation
            ):
                return False
            company = policy.company_policy(policy_path)
            policy._queue_schema(connection)
            if not _permitted(preference, company, expected_revision, expected_generation):
                connection.execute("DELETE FROM pending")
                connection.execute("DELETE FROM producer_budget")
                connection.commit()
                if not preference["enabled"]:
                    _remember_exhaustion(root, [], day, disabled=True)
                return False
            _prune(connection, day, company["metric_groups"])
            existing = {row[0] for row in connection.execute("SELECT cell FROM pending")}
            recorded = False
            exhausted = []
            for scope, cells in observations:
                cells = tuple(
                    cell for cell in cells if describe(cell)["group"] in company["metric_groups"]
                )
                limit = CATALOG["limits"][
                    "resource_observations_per_day"
                    if scope >= 512
                    else "observations_per_workflow_day"
                ]
                previous = connection.execute(
                    "SELECT count FROM producer_budget WHERE scope=?", (scope,)
                ).fetchone()
                if previous is not None and previous[0] >= limit:
                    exhausted.append(scope)
                if (
                    not cells
                    or (previous is not None and previous[0] >= limit)
                    or len(existing.union(cells)) > policy.MAX_PENDING
                ):
                    continue
                connection.execute(
                    "INSERT INTO producer_budget VALUES (?, 1, ?) ON CONFLICT(scope) DO UPDATE SET count=count+1",
                    (scope, day),
                )
                if (previous[0] if previous is not None else 0) + 1 >= limit:
                    exhausted.append(scope)
                connection.executemany(
                    "INSERT INTO pending VALUES (?, 1, ?) ON CONFLICT(cell) DO UPDATE SET "
                    "count=CASE WHEN window_day=excluded.window_day THEN min(count+1, ?) ELSE 1 END, "
                    "window_day=excluded.window_day",
                    [(cell, day, CATALOG["limits"]["count_per_cell_day"]) for cell in cells],
                )
                existing.update(cells)
                recorded = True
            connection.commit()
            _remember_exhaustion(root, exhausted, day)
            return recorded
    except (OSError, sqlite3.Error, policy.PolicyError, MeasurementError, OverflowError):
        # No raw exception, path, label or diagnostic is logged or requeued.
        return False


def preview(root: Path | None = None, *, policy_path: Path | None = None) -> list[dict]:
    """Private bounded local inspection, not an outbound report or event history."""
    root = root if root is not None else policy.default_directory()
    current = policy.status(root, policy_path=policy_path)
    if not current["effective_enabled"]:
        return []
    try:
        with closing(policy._connect(root / policy.DATABASE_NAME, readonly=True)) as connection:
            connection.execute("BEGIN")
            preference = policy._preferences(connection)
            if not _permitted(
                preference,
                policy.company_policy(policy_path),
                current["revision"],
                current["store_generation"],
            ):
                return []
            day = _day()
            rows = connection.execute(
                "SELECT cell, count, window_day FROM pending ORDER BY cell LIMIT 513"
            ).fetchall()
            if len(rows) > policy.MAX_PENDING:
                return []
            result = []
            for cell, count, window_day in rows:
                if (
                    type(count) is not int
                    or not 1 <= count <= CATALOG["limits"]["count_per_cell_day"]
                ):
                    return []
                if type(window_day) is not int or not 0 <= window_day <= 1000000:
                    return []
                described = describe(cell)
                if (
                    day - 1 <= window_day <= day
                    and described["group"] in current["company_policy"]["metric_groups"]
                ):
                    result.append({"cell": cell, **described, "count": count})
            return result
    except (OSError, sqlite3.Error, policy.PolicyError, MeasurementError):
        return []
