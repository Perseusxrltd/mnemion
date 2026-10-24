"""Shared delivery reservation and final-write fences; no network or scheduler.

The private policy database serializes Python/native reservations. A spent
attempt is never refunded, including errors, cancellation and opt-out. These
controls do not activate sending or prove a transport's actual wire cost.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import secrets
import sqlite3
import time

from . import aggregate, policy
from .wire import WireError, decode, prepare, view

DAY_MS = 86400000
WEEK_MS = 7 * DAY_MS
MAX_CLOCK_MS = 86400000000000
MAX_ATTEMPTS = 7
RESERVED_BYTES = 65536
DAILY_BYTES = 256 * 1024
DEADLINE_MS = 5000
JITTER_MS = 3600000
_FAILURES = (OSError, sqlite3.Error, policy.PolicyError, WireError, ValueError, OverflowError)


def _now_ms() -> int:
    return time.time_ns() // 1000000


def _monotonic() -> float:
    return time.monotonic()


def _integer(value, maximum=MAX_CLOCK_MS):
    return type(value) is int and 0 <= value <= maximum


def _state(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] != policy.STORAGE_VERSION:
        raise WireError
    row = connection.execute(
        "SELECT clock_ms, next_ms, lease_token, lease_deadline_ms FROM delivery_state WHERE singleton=1"
    ).fetchone()
    if (
        row is None
        or not all(_integer(row[index]) for index in (0, 1, 3))
        or (row[2] is not None and not policy.valid_generation(row[2]))
        or (row[2] is None) != (row[3] == 0)
        or row[1] < row[0]
    ):
        raise WireError
    rows = connection.execute(
        "SELECT slot, at_ms, reserved_bytes FROM delivery_attempts ORDER BY slot LIMIT 8"
    ).fetchall()
    if len(rows) > MAX_ATTEMPTS or any(
        not _integer(slot, 6)
        or not _integer(at)
        or at > row[0]
        or type(cost) is not int
        or cost != RESERVED_BYTES
        for slot, at, cost in rows
    ):
        raise WireError
    if rows:
        if (
            max(at for _, at, _ in rows) != row[0]
            or not row[0] + DAY_MS <= row[1] <= row[0] + DAY_MS + JITTER_MS
            or (row[2] is not None and row[3] != row[0] + DEADLINE_MS)
        ):
            raise WireError
    elif row != (0, 0, None, 0):
        raise WireError
    return row, rows


def budget_status(connection=None):
    """Local control counters only; no lease token or exact attempt timestamp."""
    result = {
        "state": "not_initialized",
        "maximum_attempts_per_rolling_week": MAX_ATTEMPTS,
        "minimum_attempt_spacing_seconds": DAY_MS // 1000,
        "wire_reservation_per_attempt_bytes": RESERVED_BYTES,
        "wire_budget_per_rolling_day_bytes": DAILY_BYTES,
        "attempts_in_rolling_week": 0,
        "reserved_wire_bytes_in_rolling_day": 0,
        "transport_available": False,
    }
    if connection is None:
        return result
    if connection.execute("PRAGMA user_version").fetchone()[0] != policy.STORAGE_VERSION:
        return {
            **result,
            "state": "upgrade_required",
            "attempts_in_rolling_week": None,
            "reserved_wire_bytes_in_rolling_day": None,
        }
    state, spent = _state(connection)
    now = _now_ms()
    if not _integer(now):
        raise WireError
    result.update(
        state="clock_rollback"
        if now < state[0]
        else "in_flight"
        if state[2] and now < state[3]
        else "cooldown"
        if now < state[1]
        else "ready",
        attempts_in_rolling_week=sum(at > now - WEEK_MS for _, at, _ in spent),
        reserved_wire_bytes_in_rolling_day=sum(cost for _, at, cost in spent if at > now - DAY_MS),
    )
    return result


class PreparedReport:
    """Process-local, erasable one-use report; tokens never enter its body."""

    __slots__ = (
        "_body",
        "_token",
        "revision",
        "generation",
        "deadline_ms",
        "_monotonic_deadline",
        "_used",
        "_closed",
        "_group",
        "_claim_lock",
        "_claimed",
        "_transport_claimed",
    )

    def __init__(self, body, token, revision, generation, deadline, monotonic_deadline):
        self._body = bytearray(body)
        self._token = token
        self.revision, self.generation, self.deadline_ms = revision, generation, deadline
        self._monotonic_deadline = monotonic_deadline
        self._used = False
        self._closed = False
        self._group = view(decode(body)[0])["group"]
        from threading import Lock

        self._claim_lock = Lock()
        self._claimed = False
        self._transport_claimed = False

    def claim_transport(self):
        with self._claim_lock:
            if self._transport_claimed or self._used or self._closed:
                return False
            self._transport_claimed = True
            return True

    def claim_handoff(self):
        with self._claim_lock:
            if self._claimed or self._used or self._closed:
                return False
            self._claimed = True
            return True

    def erase_body(self):
        self._body[:] = b"\0" * len(self._body)

    def clear(self):
        self.erase_body()
        self._token = ""
        self._used = True
        self._closed = True

    def preview(self):
        from .wire import preview

        if self._used:
            return None
        return preview(bytes(self._body))


class DeliveryBudget:
    """One existing private policy store, with no new persistent worker.

    The future transport must supply fresh network/pressure observations; an
    unknown or metered connection never receives a reservation. ``guarded_write``
    is only for a reviewed synchronous, nonblocking socket handoff, never DNS,
    TLS negotiation, HTTP response waiting, user callbacks or an async function.
    """

    def __init__(self, root: Path | None = None, *, policy_path: Path | None = None):
        self.root = root if root is not None else policy.default_directory()
        self.policy_path = policy_path

    def _open(self, *, readonly=False):
        policy._root_safe(self.root)
        path = self.root / policy.DATABASE_NAME
        if not policy._file_safe(path):
            raise WireError
        return policy._connect(path, readonly=readonly)

    def reserve(
        self,
        *,
        expected_revision: int,
        expected_generation: str,
        network: str = "unknown",
        constrained: bool = True,
        cohorts: dict | None = None,
    ) -> PreparedReport | None:
        if (
            not policy.COLLECTION_AVAILABLE
            or policy.COLLECTOR_URL is None
            or network != "unmetered"
            or constrained is not False
            or not _integer(expected_revision, 2147483646)
            or not policy.valid_generation(expected_generation)
        ):
            return None
        started = _monotonic()
        try:
            now = _now_ms()
            if not _integer(now, MAX_CLOCK_MS - DAY_MS - JITTER_MS):
                return None
            with closing(self._open()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                preference = policy._preferences(connection)
                company = policy.company_policy(self.policy_path)
                if not aggregate._permitted(
                    preference, company, expected_revision, expected_generation
                ):
                    return None
                policy._queue_schema(connection)
                state, spent = _state(connection)
                # Backward clocks never prune spending or restore allowance.
                if now < state[0] or now < state[1] or (state[2] and now < state[3]):
                    return None
                recent = [row for row in spent if row[1] > now - WEEK_MS]
                if (
                    len(recent) >= MAX_ATTEMPTS
                    or sum(cost for _, at, cost in recent if at > now - DAY_MS) + RESERVED_BYTES
                    > DAILY_BYTES
                ):
                    return None
                aggregate._prune(connection, now // DAY_MS, company["metric_groups"])
                rows = connection.execute("SELECT cell, count FROM pending LIMIT 513").fetchall()
                if not rows:
                    return None
                # Prepare before durable spending. Entropy/encoding failure has
                # no exposure, while every returned reservation is fully spent.
                body = prepare(rows, groups=company["metric_groups"], cohorts=cohorts)
                token = secrets.token_hex(16)
                jitter = secrets.randbelow(JITTER_MS + 1)
                if not _integer(jitter, JITTER_MS):
                    return None
                if _monotonic() - started >= DEADLINE_MS / 1000:
                    return None
                connection.execute(
                    "DELETE FROM delivery_attempts WHERE at_ms <= ?", (now - WEEK_MS,)
                )
                slot = next(
                    index
                    for index in range(MAX_ATTEMPTS)
                    if index not in {row[0] for row in recent}
                )
                connection.execute(
                    "INSERT INTO delivery_attempts VALUES (?, ?, ?)", (slot, now, RESERVED_BYTES)
                )
                connection.execute(
                    "UPDATE delivery_state SET clock_ms=?, next_ms=?, lease_token=?, lease_deadline_ms=? WHERE singleton=1",
                    (now, now + DAY_MS + jitter, token, now + DEADLINE_MS),
                )
                # A reservation consumes this queue. It can never be replayed
                # after a failed attempt, crash, cancellation or re-enable.
                connection.execute("DELETE FROM pending")
                connection.commit()
            return PreparedReport(
                body,
                token,
                expected_revision,
                expected_generation,
                now + DEADLINE_MS,
                started + DEADLINE_MS / 1000,
            )
        except _FAILURES:
            return None

    def _current(self, connection, report):
        if type(report) is not PreparedReport or report._closed:
            return False
        now = _now_ms()
        state, _ = _state(connection)
        preference = policy._preferences(connection)
        company = policy.company_policy(self.policy_path)
        return (
            _integer(now)
            and _monotonic() < report._monotonic_deadline
            and state[0] <= now < state[3]
            and state[3] == report.deadline_ms
            and state[2] == report._token
            and report._group in company["metric_groups"]
            and aggregate._permitted(preference, company, report.revision, report.generation)
        )

    def current(self, report: PreparedReport) -> bool:
        valid = False
        try:
            if policy.COLLECTION_AVAILABLE and policy.COLLECTOR_URL is not None:
                with closing(self._open(readonly=True)) as connection:
                    connection.execute("BEGIN")
                    valid = self._current(connection, report)
        except _FAILURES:
            pass
        if not valid and type(report) is PreparedReport:
            self.cancel(report)
        return valid

    def cancel(self, report: PreparedReport) -> None:
        if type(report) is not PreparedReport:
            return
        token = report._token
        report.clear()
        if not policy.valid_generation(token):
            return
        try:
            with closing(self._open()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                _state(connection)
                connection.execute(
                    "UPDATE delivery_state SET lease_token=NULL, lease_deadline_ms=0 WHERE singleton=1 AND lease_token=?",
                    (token,),
                )
                connection.commit()
        except _FAILURES:
            pass

    def guarded_write(self, report: PreparedReport, write) -> bool:
        """Serialize one nonblocking packet handoff with an explicit opt-out.

        No awaits or connection setup may run under this short database lock.
        The body is consumed on any outcome and the attempt stays spent. A
        successful handoff retains its lease for in-flight cancellation; the
        transport must finish with ``cancel`` even after a successful response.
        Bytes already handed to a transport cannot be recalled by this fence.
        """
        if type(report) is not PreparedReport or not callable(write) or not report.claim_handoff():
            return False
        from inspect import iscoroutinefunction

        if iscoroutinefunction(write):
            self.cancel(report)
            return False
        result, owned = False, False
        try:
            with closing(self._open()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if report._used:
                    return False
                owned = True
                if not self._current(connection, report):
                    return False
                # Burn the process-local handle before invoking the trusted
                # transport, including recursive calls or a thrown exception.
                report._used = True
                try:
                    result = write(bytes(report._body)) is True
                except Exception:
                    result = False
                connection.commit()
        except _FAILURES:
            result = False
        finally:
            if owned or not report._used:
                report.erase_body()
                if not result:
                    self.cancel(report)
        return result

    async def watch(self, report: PreparedReport, abort) -> None:
        """Only during an existing attempt; no idle task or scheduled wake.

        The transport owns cancellation of this task on success or shutdown.
        It must also call the final-write fence, not rely on periodic checks.
        """
        import asyncio

        try:
            while self.current(report):
                await asyncio.sleep(0.025)
            try:
                abort()
            except Exception:
                # Optional transport cleanup must not expose its exception or
                # interrupt a caller's canonical memory operation.
                pass
        finally:
            self.cancel(report)
