"""Reviewed source defaults and immutable policies attached to device grants.

Policy changes share the acceptance/revocation lock. An idempotent transition
never revokes grants created after its first committed attempt. No memory,
receipt, source identity, audience or deletion fence is rewritten here.
"""

from contextlib import contextmanager
import hashlib
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ..capture_identity import canonical_capture_json
from .db import require_administrator
from .errors import ServiceError, not_found
from .models import json_value
from .repository import audit
from .request_replay import observed


def version_value(row):
    return json_value(
        {
            key: row[key]
            for key in (
                "source_id",
                "policy_version",
                "capture_mode",
                "capture_policy",
                "created_at",
                "transition_id",
                "previous_grants",
                "affected_grants",
                "approved_by",
            )
        }
    )


class CapturePolicies:
    @contextmanager
    def _policy_authority(self, identity, connector_id, source_id):
        from .capture_custody import source_lock

        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            source_lock(conn, source_id)
            self.db._check_identity(conn, identity)
            row = conn.execute(
                "SELECT * FROM mnemion.capture_sources WHERE source_id=%s AND connector_id=%s",
                (source_id, connector_id),
            ).fetchone()
            if not row:
                raise not_found()
            yield conn, row

    def source_list(self, identity, connector_id, *, after=None, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Choose a bounded source page")
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            rows = conn.execute(
                """SELECT * FROM mnemion.capture_sources WHERE connector_id=%s
                   AND (%s::uuid IS NULL OR source_id>%s) ORDER BY source_id LIMIT %s""",
                (connector_id, after, after, limit + 1),
            ).fetchall()
            return {
                "items": [self._source_value(conn, row) for row in rows[:limit]],
                "next_cursor": str(rows[limit - 1]["source_id"]) if len(rows) > limit else None,
            }

    def _policy_review(self, conn, source, *, after=None, limit=100):
        digest = hashlib.sha256(
            canonical_capture_json(
                ["mnemion-capture-policy-review-v1", str(source["source_id"]), source["version"]]
            )
        )
        devices, unrevoked, active, more = [], 0, 0, False
        # The review includes every unrevoked grant, even if its key currently
        # cannot authenticate. Its rendered device page and working RAM are bounded.
        with conn.cursor(name="capture_review_" + uuid4().hex) as cursor:
            cursor.execute(
                """SELECT g.grant_id,g.device_key_id,k.name AS device_name,g.policy_version,g.created_at,
                          k.revoked_at AS key_revoked,k.expires_at AS key_expires,
                          c.disabled_at AS connector_disabled,p.disabled_at AS principal_disabled,
                          p.administrator,
                          (s.revoked_at IS NULL AND c.disabled_at IS NULL AND p.disabled_at IS NULL
                           AND NOT p.administrator AND k.revoked_at IS NULL
                           AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())) AS active
                   FROM mnemion.capture_grants g JOIN mnemion.capture_sources s USING(tenant_id,source_id)
                     JOIN mnemion.api_keys k ON k.tenant_id=g.tenant_id AND k.id=g.device_key_id
                     JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
                     JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
                   WHERE g.source_id=%s AND g.revoked_at IS NULL ORDER BY g.grant_id""",
                (source["source_id"],),
            )
            for row in cursor:
                digest.update(
                    canonical_capture_json(
                        json_value({k: v for k, v in row.items() if k != "active"})
                    )
                )
                unrevoked += 1
                active += bool(row["active"])
                if after is not None and row["grant_id"] <= UUID(str(after)):
                    continue
                if len(devices) < limit:
                    devices.append(
                        json_value(
                            {
                                key: row[key]
                                for key in (
                                    "grant_id",
                                    "device_key_id",
                                    "device_name",
                                    "policy_version",
                                    "created_at",
                                    "active",
                                )
                            }
                        )
                    )
                else:
                    more = True
        return {
            "source": self._source_value(conn, source),
            "review_token": digest.hexdigest(),
            "unrevoked_grants": unrevoked,
            "active_grants": active,
            "devices": devices,
            "next_cursor": devices[-1]["grant_id"] if more else None,
        }

    def policy_review(self, identity, connector_id, source_id, *, after=None, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Choose a bounded device page")
        with self._policy_authority(identity, connector_id, source_id) as (conn, source):
            return self._policy_review(conn, source, after=after, limit=limit)

    def policy_versions(self, identity, connector_id, source_id, *, after=0, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100 or type(after) is not int or after < 0:
            raise ValueError("Choose a bounded policy page")
        with self._policy_authority(identity, connector_id, source_id) as (conn, _):
            rows = conn.execute(
                """SELECT * FROM mnemion.capture_policy_versions WHERE source_id=%s
                   AND policy_version>%s ORDER BY policy_version LIMIT %s""",
                (source_id, after, limit + 1),
            ).fetchall()
            return {
                "items": [version_value(row) for row in rows[:limit]],
                "next_cursor": rows[limit - 1]["policy_version"] if len(rows) > limit else None,
            }

    def change_policy(self, identity, connector_id, source_id, transition_id, command):
        request_hash = hashlib.sha256(
            canonical_capture_json(command.model_dump(mode="json"))
        ).hexdigest()
        with self._policy_authority(identity, connector_id, source_id) as (conn, source):
            previous = conn.execute(
                "SELECT * FROM mnemion.capture_policy_versions WHERE transition_id=%s",
                (transition_id,),
            ).fetchone()
            if previous:
                if previous["source_id"] != source_id or previous["request_hash"] != request_hash:
                    raise ServiceError(
                        409,
                        "capture_transition_conflict",
                        "Keep the same reviewed request for this transition.",
                    )
                observed(True)
                return {
                    "source": self._source_value(conn, source),
                    "transition": version_value(previous),
                }
            if source["revoked_at"]:
                raise ServiceError(
                    409,
                    "capture_source_retired",
                    "A retired source cannot receive a new capture policy.",
                )
            review = self._policy_review(conn, source)
            if (
                command.expected_version != source["version"]
                or command.review_token != review["review_token"]
            ):
                raise ServiceError(
                    409,
                    "capture_review_changed",
                    "Source settings or device permissions changed; review them again.",
                )
            policy = command.capture_policy.model_dump(mode="json")
            if source["capture_policy"] == policy:
                raise ServiceError(
                    409,
                    "capture_policy_unchanged",
                    "Choose a changed capture policy before creating a revision.",
                )
            version = source["policy_version"] + 1
            row = conn.execute(
                """INSERT INTO mnemion.capture_policy_versions
                     (tenant_id,source_id,policy_version,capture_mode,capture_policy,transition_id,
                      request_hash,previous_grants,affected_grants,approved_by)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (
                    identity.tenant_id,
                    source_id,
                    version,
                    command.capture_policy.capture_mode,
                    Jsonb(policy),
                    transition_id,
                    request_hash,
                    command.previous_grants,
                    review["unrevoked_grants"],
                    identity.principal_id,
                ),
            ).fetchone()
            if command.previous_grants == "revoke":
                conn.execute(
                    "UPDATE mnemion.capture_grants SET revoked_at=now() WHERE source_id=%s AND revoked_at IS NULL",
                    (source_id,),
                )
            source = conn.execute(
                """UPDATE mnemion.capture_sources SET policy_version=%s,capture_mode=%s,
                   capture_policy=%s,version=version+1 WHERE source_id=%s RETURNING *""",
                (version, command.capture_policy.capture_mode, Jsonb(policy), source_id),
            ).fetchone()
            audit(
                conn,
                identity,
                "capture.policy_changed",
                source_id,
                details={
                    "transition_id": transition_id,
                    "policy_version": version,
                    "previous_grants": command.previous_grants,
                    "affected_grants": review["unrevoked_grants"],
                },
            )
            observed(False)
            return {"source": self._source_value(conn, source), "transition": version_value(row)}
