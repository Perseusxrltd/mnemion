"""Private transactional grants and durable work outside the memory database.

No request can confer OS authority. The owning account creates this store and
the restricted SSH receiver supplies the authenticated operator identity.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from .. import local_state
from ..private_output import private_output
from . import HostControlError
from .protocol import ROLES, Operator, canonical, fingerprint, timestamp, parse

MAX_OPERATORS = 128
MAX_OPERATOR_RECORDS = 512
MAX_OPERATIONS = 512
RESERVED_AUTHORITY_OPERATIONS = 128
MAX_AUDIT = 1024
STORE_FORMAT = 2
SCHEMA = """
CREATE TABLE host (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    id TEXT NOT NULL UNIQUE,
    service_identity TEXT NOT NULL,
    service_state TEXT NOT NULL,
    service_desired TEXT NOT NULL DEFAULT 'running' CHECK(service_desired IN ('running','stopped')),
    service_operation TEXT,
    service_changed_at TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE operators (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    public_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK(role IN ('observer','operator','custodian')),
    revision INTEGER NOT NULL DEFAULT 1,
    expires_at TEXT,
    revoked_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE operations (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    actor TEXT NOT NULL REFERENCES operators(id),
    actor_revision INTEGER NOT NULL,
    request_sha256 TEXT NOT NULL,
    request TEXT NOT NULL,
    action TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    phase TEXT NOT NULL CHECK(phase IN
        ('queued','running','succeeded','failed','cancelled','inspection_required')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    result TEXT,
    error TEXT,
    private_context TEXT,
    effect_started_at TEXT
);
CREATE TABLE audit (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT,
    event TEXT NOT NULL,
    subject TEXT
);
PRAGMA user_version=2;
"""


def identifier(value) -> str:
    try:
        result = str(UUID(str(value)))
        if str(value) != result:
            raise ValueError
        return result
    except (ValueError, TypeError, AttributeError):
        raise HostControlError(
            "invalid_identity", "Use a canonical host or operator identity."
        ) from None


def _active(row, now: str) -> bool:
    return (
        row is not None
        and row["revoked_at"] is None
        and (row["expires_at"] is None or row["expires_at"] > now)
    )


def _audit(conn, actor, event, subject=None):
    conn.execute(
        "INSERT INTO audit(at,actor,event,subject) VALUES(?,?,?,?)",
        (timestamp(), actor, event, subject),
    )
    conn.execute(
        "DELETE FROM audit WHERE sequence NOT IN (SELECT sequence FROM audit ORDER BY sequence DESC LIMIT ?)",
        (MAX_AUDIT,),
    )


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).absolute()
        local_state._regular(self.root, directory=True)
        self.path = self.root / "authority.sqlite3"
        local_state._regular(self.path)

    @contextmanager
    def transaction(self):
        local_state._regular(self.root, directory=True)
        local_state._regular(self.path)
        conn = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA max_page_count=8192")
            if conn.execute("PRAGMA user_version").fetchone()[0] != STORE_FORMAT:
                raise HostControlError(
                    "unsupported_store", "The host control store needs inspection."
                )
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
            raise HostControlError(
                "host_control_unavailable",
                "Host control storage is busy or unavailable; inspect status before retrying.",
            ) from None
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def adopt(
        cls,
        root: Path,
        service_state: Path,
        service_identity: str,
        operator: Operator,
        *,
        service_running: bool = True,
    ):
        if os.name != "posix" or os.geteuid() == 0:
            raise HostControlError(
                "unsupported_host",
                "Adopt this host from its unprivileged Linux or macOS service account.",
            )
        if operator.role != "custodian" or operator.expires_at is not None:
            raise HostControlError(
                "custodian_required",
                "The first independently held operator key must be a permanent custodian.",
            )
        if type(service_running) is not bool:
            raise HostControlError("invalid_state", "Observe the existing memory service first.")
        root = local_state.directory(root, exist_ok=False)
        service_state = Path(service_state).absolute()
        local_state._regular(service_state, directory=True)
        path = root / "authority.sqlite3"
        host_id, operator_id = str(uuid4()), str(uuid4())
        with private_output(path):
            pass
        conn = sqlite3.connect(path)
        try:
            conn.execute("PRAGMA synchronous=FULL")
            conn.executescript(SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO host(singleton,id,service_identity,service_state,service_desired,service_changed_at,created_at) VALUES(1,?,?,?,?,?,?)",
                (
                    host_id,
                    service_identity,
                    str(service_state),
                    "running" if service_running else "stopped",
                    timestamp(),
                    timestamp(),
                ),
            )
            cls._insert_operator(conn, operator_id, operator)
            _audit(conn, operator_id, "host_adopted", host_id)
            conn.commit()
        finally:
            conn.close()
        return cls(root), {"host_id": host_id, "operator_id": operator_id, "revision": 1}

    @staticmethod
    def _insert_operator(conn, operator_id, spec):
        conn.execute(
            "INSERT INTO operators(id,name,public_key,fingerprint,role,expires_at,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                operator_id,
                spec.name,
                spec.public_key,
                fingerprint(spec.public_key),
                spec.role,
                spec.expires_at.isoformat(timespec="microseconds") if spec.expires_at else None,
                timestamp(),
            ),
        )

    @staticmethod
    def authorize(conn, actor, host_id, action):
        host = conn.execute("SELECT * FROM host WHERE singleton=1").fetchone()
        actor, host_id = identifier(actor), identifier(host_id)
        row = conn.execute("SELECT * FROM operators WHERE id=?", (actor,)).fetchone()
        if host is None or host["id"] != host_id or not _active(row, timestamp()):
            raise HostControlError(
                "host_access_denied", "Current authority for this host is required."
            )
        if action not in ROLES[row["role"]]:
            raise HostControlError(
                "host_access_denied", "This operator is not allowed to perform that action."
            )
        return host, row

    def authority(self, actor, host_id):
        with self.transaction() as conn:
            host, operator = self.authorize(conn, actor, host_id, "host.status")
            return {
                "host_id": host["id"],
                "revision": host["revision"],
                "observed_at": timestamp(),
                "operator": {
                    key: operator[key]
                    for key in ("id", "name", "fingerprint", "role", "revision", "expires_at")
                },
                "actions": sorted(ROLES[operator["role"]]),
            }

    def authenticate(self, public_key):
        """Map a cryptographically authenticated key to its current enrollment."""
        key_id = fingerprint(public_key)
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM operators WHERE fingerprint=?", (key_id,)).fetchone()
            if not _active(row, timestamp()):
                raise HostControlError(
                    "host_access_denied", "Current host operator enrollment is required."
                )
            return row["id"]

    def host_record(self):
        """Private OS-owner adapter input; never a remote status response."""
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM host WHERE singleton=1").fetchone()
            if row is None:
                raise HostControlError(
                    "host_control_unavailable", "Inspect the adopted host identity."
                )
            return dict(row)

    def operators(self, actor, host_id, *, limit=50, offset=0):
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or not 0 <= offset <= 8192
        ):
            raise HostControlError("invalid_request", "Use a bounded operator page.")
        with self.transaction() as conn:
            host, _ = self.authorize(conn, actor, host_id, "operators.list")
            rows = conn.execute(
                "SELECT id,name,fingerprint,role,revision,expires_at,revoked_at,created_at FROM operators ORDER BY created_at,id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT count(*) FROM operators").fetchone()[0]
            return {
                "revision": host["revision"],
                "operators": [dict(row) for row in rows],
                "total": total,
                "next_offset": offset + len(rows) if offset + len(rows) < total else None,
            }

    @staticmethod
    def _space(conn, limit):
        count = conn.execute("SELECT count(*) FROM operations").fetchone()[0]
        if count >= limit:
            # Only expired, completed work may leave the bounded receipt history.
            # Exact replay of that old request is then refused by its lifetime;
            # uncertain/running work never becomes executable again by pruning.
            conn.execute(
                "DELETE FROM operations WHERE id IN (SELECT id FROM operations WHERE phase IN ('succeeded','failed','cancelled') AND valid_until<=? ORDER BY sequence LIMIT ?)",
                (timestamp(), count - limit + 1),
            )
        if conn.execute("SELECT count(*) FROM operations").fetchone()[0] >= limit:
            raise HostControlError(
                "operation_limit",
                "Host work is at its bounded capacity. Inspect pending work or wait for completed approvals to expire.",
            )

    @staticmethod
    def _existing(conn, actor, request):
        digest = hashlib.sha256(canonical(request.model_dump(mode="json"))).hexdigest()
        row = conn.execute(
            "SELECT * FROM operations WHERE id=?", (str(request.request_id),)
        ).fetchone()
        if row is not None:
            if row["actor"] != str(actor) or row["request_sha256"] != digest:
                raise HostControlError(
                    "operation_conflict", "This operation identity already names different work."
                )
            return json.loads(row["result"])
        request.current(datetime.fromisoformat(timestamp()))
        Store._space(conn, MAX_OPERATIONS)
        return None

    @staticmethod
    def _receipt(conn, actor, request, result):
        payload = canonical(request.model_dump(mode="json"))
        revision = conn.execute(
            "SELECT revision FROM operators WHERE id=?", (str(actor),)
        ).fetchone()[0]
        at = timestamp()
        conn.execute(
            "INSERT INTO operations(id,actor,actor_revision,request_sha256,request,action,valid_until,phase,created_at,updated_at,result) VALUES(?,?,?,?,?,?,?,'succeeded',?,?,?)",
            (
                str(request.request_id),
                str(actor),
                revision,
                hashlib.sha256(payload).hexdigest(),
                payload.decode(),
                request.action,
                request.valid_until.isoformat(timespec="microseconds"),
                at,
                at,
                canonical(result).decode(),
            ),
        )
        return result

    def grant(self, actor, request):
        with self.transaction() as conn:
            host, _ = self.authorize(conn, actor, request.host_id, request.action)
            if (previous := self._existing(conn, actor, request)) is not None:
                return previous
            if host["revision"] != request.expected_revision:
                raise HostControlError(
                    "authority_changed", "Refresh operator authority before changing it."
                )
            spec = request.operator
            if spec.expires_at is not None and spec.expires_at <= datetime.now(timezone.utc):
                raise HostControlError(
                    "invalid_expiry", "An operator grant must expire in the future."
                )
            if (
                conn.execute(
                    "SELECT count(*) FROM operators WHERE revoked_at IS NULL AND (expires_at IS NULL OR expires_at>?)",
                    (timestamp(),),
                ).fetchone()[0]
                >= MAX_OPERATORS
            ):
                raise HostControlError(
                    "operator_limit",
                    "Retire an unused enrollment before adding another active operator.",
                )
            if conn.execute("SELECT count(*) FROM operators").fetchone()[0] >= MAX_OPERATOR_RECORDS:
                conn.execute(
                    "DELETE FROM operators WHERE (revoked_at IS NOT NULL OR expires_at<=?) AND id NOT IN (SELECT actor FROM operations)",
                    (timestamp(),),
                )
            if conn.execute("SELECT count(*) FROM operators").fetchone()[0] >= MAX_OPERATOR_RECORDS:
                raise HostControlError(
                    "operator_limit",
                    "Retained operator receipts need inspection before adding more enrollments.",
                )
            if conn.execute(
                "SELECT 1 FROM operators WHERE fingerprint=?", (fingerprint(spec.public_key),)
            ).fetchone():
                raise HostControlError(
                    "operator_key_used",
                    "Each operator enrollment needs an independently held new key.",
                )
            operator_id = str(uuid4())
            self._insert_operator(conn, operator_id, spec)
            conn.execute("UPDATE host SET revision=revision+1 WHERE singleton=1")
            _audit(conn, str(actor), "operator_granted", operator_id)
            return self._receipt(
                conn,
                actor,
                request,
                {
                    "operator_id": operator_id,
                    "revision": host["revision"] + 1,
                    "fingerprint": fingerprint(spec.public_key),
                },
            )

    def revoke(self, actor, request):
        with self.transaction() as conn:
            host, _ = self.authorize(conn, actor, request.host_id, request.action)
            if (previous := self._existing(conn, actor, request)) is not None:
                return previous
            if host["revision"] != request.expected_revision:
                raise HostControlError(
                    "authority_changed", "Refresh operator authority before changing it."
                )
            operator_id = str(request.operator_id)
            row = conn.execute("SELECT * FROM operators WHERE id=?", (operator_id,)).fetchone()
            if row is None:
                raise HostControlError(
                    "operator_not_found", "The operator enrollment is not available."
                )
            if row["revoked_at"] is not None:
                return self._receipt(
                    conn,
                    actor,
                    request,
                    {
                        "operator_id": operator_id,
                        "revision": host["revision"],
                        "already_revoked": True,
                    },
                )
            permanent = conn.execute(
                "SELECT count(*) FROM operators WHERE id<>? AND role='custodian' AND revoked_at IS NULL AND expires_at IS NULL",
                (operator_id,),
            ).fetchone()[0]
            if not permanent:
                raise HostControlError(
                    "last_custodian", "Enroll another permanent custodian before retiring this key."
                )
            at = timestamp()
            conn.execute(
                "UPDATE operators SET revoked_at=?,revision=revision+1 WHERE id=?",
                (at, operator_id),
            )
            conn.execute("UPDATE host SET revision=revision+1 WHERE singleton=1")
            conn.execute(
                "UPDATE operations SET phase='cancelled',updated_at=?,error='operator_retired' WHERE actor=? AND phase='queued'",
                (at, operator_id),
            )
            _audit(conn, str(actor), "operator_revoked", operator_id)
            return self._receipt(
                conn, actor, request, {"operator_id": operator_id, "revision": host["revision"] + 1}
            )

    @staticmethod
    def _operation(row):
        return {
            "operation_id": row["id"],
            "operator_id": row["actor"],
            "action": row["action"],
            "phase": row["phase"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "valid_until": row["valid_until"],
            "effect_started_at": row["effect_started_at"],
            "result": json.loads(row["result"]) if row["result"] is not None else None,
            "error": row["error"],
        }

    def enqueue(self, actor, request):
        if request.action not in {
            "service.start",
            "service.stop",
            "backup.create",
            "backup.verify",
            "upgrade.plan",
            "upgrade.apply",
            "operations.resolve",
        }:
            raise HostControlError("invalid_action", "Choose a documented host job.")
        payload = canonical(request.model_dump(mode="json"))
        digest = hashlib.sha256(payload).hexdigest()
        with self.transaction() as conn:
            _, operator = self.authorize(conn, actor, request.host_id, request.action)
            operation_id = str(request.request_id)
            row = conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is not None:
                if row["actor"] != str(actor) or row["request_sha256"] != digest:
                    raise HostControlError(
                        "operation_conflict",
                        "This operation identity already names different work.",
                    )
                return self._operation(row)
            request.current(datetime.fromisoformat(timestamp()))
            self._space(conn, MAX_OPERATIONS - RESERVED_AUTHORITY_OPERATIONS)
            at = timestamp()
            conn.execute(
                "INSERT INTO operations(id,actor,actor_revision,request_sha256,request,action,valid_until,phase,created_at,updated_at) VALUES(?,?,?,?,?,?,?,'queued',?,?)",
                (
                    operation_id,
                    str(actor),
                    operator["revision"],
                    digest,
                    payload.decode(),
                    request.action,
                    request.valid_until.isoformat(timespec="microseconds"),
                    at,
                    at,
                ),
            )
            _audit(conn, str(actor), "operation_queued", operation_id)
            return self._operation(
                conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            )

    def operation(self, actor, host_id, operation_id):
        with self.transaction() as conn:
            _, operator = self.authorize(conn, actor, host_id, "operations.get")
            row = conn.execute(
                "SELECT * FROM operations WHERE id=?", (identifier(operation_id),)
            ).fetchone()
            if row is None or (row["actor"] != str(actor) and operator["role"] != "custodian"):
                raise HostControlError(
                    "operation_not_found", "This host operation is not available to this operator."
                )
            return self._operation(row)

    def operations(self, actor, host_id, *, limit=50, offset=0):
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or not 0 <= offset <= 8192
        ):
            raise HostControlError("invalid_request", "Use a bounded operation page.")
        with self.transaction() as conn:
            _, operator = self.authorize(conn, actor, host_id, "operations.list")
            all_operations = operator["role"] == "custodian"
            rows = conn.execute(
                """SELECT id AS operation_id,actor AS operator_id,action,phase,created_at,
                updated_at,valid_until,effect_started_at,error,result IS NOT NULL AS has_result
                FROM operations WHERE (?=1 OR actor=?) ORDER BY sequence DESC LIMIT ? OFFSET ?""",
                (int(all_operations), str(actor), limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT count(*) FROM operations WHERE (?=1 OR actor=?)",
                (int(all_operations), str(actor)),
            ).fetchone()[0]
            return {
                "operations": [
                    {**dict(row), "has_result": bool(row["has_result"])} for row in rows
                ],
                "total": total,
                "next_offset": offset + len(rows) if offset + len(rows) < total else None,
            }

    def claim(self):
        """Only the independent owning worker calls this, under its lifetime lock."""
        with self.transaction() as conn:
            if conn.execute("SELECT 1 FROM operations WHERE phase='running' LIMIT 1").fetchone():
                return None
            blocked = (
                conn.execute(
                    "SELECT 1 FROM operations WHERE phase='inspection_required' LIMIT 1"
                ).fetchone()
                is not None
            )
            for row in conn.execute(
                "SELECT * FROM operations WHERE phase='queued' ORDER BY sequence"
            ).fetchall():
                if row["valid_until"] <= timestamp():
                    conn.execute(
                        "UPDATE operations SET phase='cancelled',updated_at=?,error='request_expired' WHERE id=?",
                        (timestamp(), row["id"]),
                    )
                    _audit(conn, row["actor"], "operation_expired", row["id"])
                    continue
                if blocked and row["action"] not in {
                    "upgrade.plan",
                    "upgrade.apply",
                    "backup.verify",
                    "operations.resolve",
                }:
                    continue
                operator = conn.execute(
                    "SELECT * FROM operators WHERE id=?", (row["actor"],)
                ).fetchone()
                if (
                    not _active(operator, timestamp())
                    or operator["revision"] != row["actor_revision"]
                    or row["action"] not in ROLES[operator["role"]]
                ):
                    conn.execute(
                        "UPDATE operations SET phase='cancelled',updated_at=?,error='authority_changed' WHERE id=?",
                        (timestamp(), row["id"]),
                    )
                    _audit(conn, row["actor"], "operation_cancelled", row["id"])
                    continue
                conn.execute(
                    "UPDATE operations SET phase='running',updated_at=? WHERE id=?",
                    (timestamp(), row["id"]),
                )
                _audit(conn, row["actor"], "operation_started", row["id"])
                return {
                    "operation_id": row["id"],
                    "actor": row["actor"],
                    "request": json.loads(row["request"]),
                }
            return None

    def has_pending(self):
        with self.transaction() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM operations WHERE phase IN ('queued','running','inspection_required') LIMIT 1"
                ).fetchone()
                is not None
            )

    def needs_worker(self):
        with self.transaction() as conn:
            blocked = (
                conn.execute(
                    "SELECT 1 FROM operations WHERE phase='inspection_required' LIMIT 1"
                ).fetchone()
                is not None
            )
            return (
                conn.execute(
                    """SELECT 1 FROM operations WHERE phase='running' OR
                    (phase='queued' AND (?=0 OR valid_until<=? OR
                     action IN ('upgrade.plan','upgrade.apply','backup.verify','operations.resolve'))) LIMIT 1""",
                    (int(blocked), timestamp()),
                ).fetchone()
                is not None
            )

    def uncertain(self):
        with self.transaction() as conn:
            return [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM operations WHERE phase='inspection_required' ORDER BY sequence"
                ).fetchall()
            ]

    def resolve(self, actor, request, observation):
        """Accept an observed stable state without rewriting an unknown history."""
        encoded = canonical(observation)
        if len(encoded) > 64 * 1024 or type(observation.get("running")) is not bool:
            raise HostControlError("invalid_result", "Use a bounded host-state observation.")
        with self.transaction() as conn:
            self.authorize(conn, actor, request.host_id, "operations.resolve")
            request.current(datetime.now(timezone.utc))
            row = conn.execute(
                "SELECT * FROM operations WHERE id=?", (identifier(request.operation_id),)
            ).fetchone()
            if row is None or row["phase"] != "inspection_required":
                raise HostControlError(
                    "operation_changed", "Inspect the unresolved host operation."
                )
            result = {
                "original_outcome": "unconfirmed",
                "accepted_current_state": observation,
                "resolved_by_operation": str(request.request_id),
            }
            conn.execute(
                "UPDATE operations SET phase='failed',updated_at=?,result=? WHERE id=?",
                (timestamp(), canonical(result).decode(), row["id"]),
            )
            self._service_intent(
                conn, str(request.request_id), "running" if observation["running"] else "stopped"
            )
            _audit(conn, str(actor), "uncertain_operation_resolved", row["id"])
            return {"operation_id": row["id"], **result}

    def recovered(self, original_id, recovery_id, observation):
        """Keep the old failure; link the separate successful forward recovery."""
        with self.transaction() as conn:
            old = conn.execute(
                "SELECT * FROM operations WHERE id=?", (identifier(original_id),)
            ).fetchone()
            new = conn.execute(
                "SELECT * FROM operations WHERE id=?", (identifier(recovery_id),)
            ).fetchone()
            if (
                old is None
                or old["phase"] not in {"inspection_required", "failed"}
                or new is None
                or new["phase"] != "running"
                or new["action"] != "upgrade.apply"
            ):
                raise HostControlError(
                    "operation_changed", "Inspect the original recovery receipt."
                )
            result = {
                "original_outcome": "unconfirmed",
                "recovery_operation": new["id"],
                "current_state": observation,
            }
            encoded = canonical(result)
            if len(encoded) > 64 * 1024:
                raise HostControlError("invalid_result", "Use a bounded host-state observation.")
            conn.execute(
                "UPDATE operations SET phase='failed',updated_at=?,result=? WHERE id=?",
                (timestamp(), encoded.decode(), old["id"]),
            )
            _audit(conn, new["actor"], "forward_recovery_observed", old["id"])

    def work_status(self):
        with self.transaction() as conn:
            return {
                row["phase"]: row["total"]
                for row in conn.execute(
                    "SELECT phase,count(*) AS total FROM operations GROUP BY phase"
                ).fetchall()
            }

    def service_policy(self):
        """Durable service intent survives receipt pruning and operator retirement.

        Queued/running/uncertain work excludes an external automatic repair.
        Only the guarded effect boundary changes intent, never an unexecuted
        request, expired approval, or observation of an unavailable API.
        """
        with self.transaction() as conn:
            host = conn.execute("SELECT * FROM host WHERE singleton=1").fetchone()
            pending = (
                conn.execute(
                    "SELECT 1 FROM operations WHERE phase IN ('queued','running','inspection_required') LIMIT 1"
                ).fetchone()
                is not None
            )
            return {
                "host_id": host["id"],
                "desired": host["service_desired"],
                "operation_id": host["service_operation"],
                "changed_at": host["service_changed_at"] or host["created_at"],
                "pending_work": pending,
                "automatic_start_allowed": host["service_desired"] == "running" and not pending,
            }

    @staticmethod
    def _service_intent(conn, operation_id, desired):
        conn.execute(
            "UPDATE host SET service_desired=?,service_operation=?,service_changed_at=? WHERE singleton=1",
            (desired, operation_id, timestamp()),
        )

    def plan(self, actor, host_id, operation_id):
        with self.transaction() as conn:
            _, operator = self.authorize(conn, actor, host_id, "upgrade.apply")
            row = conn.execute(
                "SELECT * FROM operations WHERE id=?", (identifier(operation_id),)
            ).fetchone()
            if (
                row is None
                or row["action"] != "upgrade.plan"
                or row["phase"] != "succeeded"
                or row["private_context"] is None
                or row["valid_until"] <= timestamp()
                or row["actor"] != str(actor)
                and operator["role"] != "custodian"
            ):
                raise HostControlError("plan_changed", "Review a fresh host upgrade plan.")
            return json.loads(row["private_context"])

    def guard(self, operation_id, *, record_effect=False):
        """Recheck current approval after a host lock wait and before cutover."""
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM operations WHERE id=?", (identifier(operation_id),)
            ).fetchone()
            if row is None or row["phase"] != "running":
                raise HostControlError("operation_changed", "Inspect the existing host operation.")
            request = parse(row["request"].encode())
            try:
                _, actor = self.authorize(conn, row["actor"], request.host_id, request.action)
            except HostControlError:
                raise HostControlError(
                    "authority_changed", "Current host authority changed."
                ) from None
            if actor["revision"] != row["actor_revision"]:
                raise HostControlError("authority_changed", "Current host authority changed.")
            request.current(datetime.now(timezone.utc))
            if record_effect and row["effect_started_at"] is None:
                conn.execute(
                    "UPDATE operations SET effect_started_at=? WHERE id=?",
                    (timestamp(), row["id"]),
                )
                _audit(conn, row["actor"], "effect_authorized", row["id"])
                if request.action in {"service.start", "service.stop", "upgrade.apply"}:
                    self._service_intent(
                        conn,
                        row["id"],
                        "stopped" if request.action == "service.stop" else "running",
                    )
                elif request.action == "operations.resolve" and request.settle == "stop":
                    self._service_intent(conn, row["id"], "stopped")
            return request

    def inspection(self, operation_id, *, result=None):
        encoded = canonical(result)
        if len(encoded) > 64 * 1024:
            raise HostControlError(
                "invalid_result", "Host-operation results must fit within 64 KiB."
            )
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM operations WHERE id=?", (identifier(operation_id),)
            ).fetchone()
            if row is None or row["phase"] != "running":
                raise HostControlError("operation_changed", "Inspect the existing host operation.")
            conn.execute(
                "UPDATE operations SET phase='inspection_required',updated_at=?,result=?,error='operation_uncertain' WHERE id=?",
                (timestamp(), encoded.decode(), row["id"]),
            )
            _audit(conn, row["actor"], "operation_needs_inspection", row["id"])

    def interrupted(self):
        """Observation only: a replacement worker must never replay running work."""
        with self.transaction() as conn:
            rows = conn.execute("SELECT id,actor FROM operations WHERE phase='running'").fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE operations SET phase='inspection_required',updated_at=?,error='worker_interrupted' WHERE id=?",
                    (timestamp(), row["id"]),
                )
                _audit(conn, row["actor"], "operation_interrupted", row["id"])
            return len(rows)

    def finish(self, operation_id, *, result=None, error=None, context=None):
        # Fixed error codes and a bounded adapter-owned summary only. Never pass
        # raw subprocess output, exception strings or connection credentials.
        if error not in {
            None,
            "host_busy",
            "host_unavailable",
            "authority_changed",
            "plan_changed",
            "backup_required",
            "backup_configuration_changed",
            "backup_not_found",
            "operation_failed",
            "request_expired",
        }:
            raise HostControlError("invalid_result", "Use a documented host-operation outcome.")
        encoded = canonical(result)
        private = canonical(context)
        if len(encoded) > 64 * 1024 or len(private) > 64 * 1024:
            raise HostControlError(
                "invalid_result", "Host-operation results must fit within 64 KiB."
            )
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM operations WHERE id=?", (identifier(operation_id),)
            ).fetchone()
            if row is None or row["phase"] != "running":
                raise HostControlError(
                    "operation_changed",
                    "Inspect the existing operation before changing its outcome.",
                )
            conn.execute(
                "UPDATE operations SET phase=?,updated_at=?,result=?,error=?,private_context=? WHERE id=?",
                (
                    "failed" if error else "succeeded",
                    timestamp(),
                    encoded.decode(),
                    error,
                    private.decode() if context is not None else None,
                    row["id"],
                ),
            )
            _audit(conn, row["actor"], "operation_finished", row["id"])
