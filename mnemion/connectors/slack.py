"""Slack read-only history and thread adapter, scoped to verified membership."""

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .http import ProviderHTTP
from .protocol import Document, Scope
from .providers import ProviderError


class SlackProvider:
    access_mode = "provider"

    def __init__(self, config, *, transport=None, sleep=None):
        self.config = config
        self.http = ProviderHTTP(
            "https://slack.com/api/",
            config.token,
            transport=transport,
            **({"sleep": sleep} if sleep else {}),
        )
        self.workspace_url = None

    def close(self):
        self.http.close()

    def call(self, method, **params):
        result = self.http.get(method, params)
        if result.get("ok") is not True:
            code = result.get("error")
            access_lost = code in {
                "invalid_auth",
                "account_inactive",
                "token_revoked",
                "not_authed",
                "channel_not_found",
                "not_in_channel",
                "missing_scope",
                "access_denied",
            }
            raise ProviderError(
                "slack_access_lost" if access_lost else "slack_request_failed",
                access_lost=access_lost,
            )
        return result

    def pages(self, method, **params):
        cursor = None
        seen = set()
        for _ in range(100000):
            response = self.call(method, **{**params, **({"cursor": cursor} if cursor else {})})
            yield response
            next_cursor = response.get("response_metadata", {}).get("next_cursor")
            if next_cursor:
                if next_cursor in seen:
                    raise ProviderError("slack_repeated_cursor")
                seen.add(next_cursor)
                cursor = next_cursor
            elif response.get("has_more"):
                # A cursor-based scan cannot certify completeness from a
                # truncated time window. Never infer deletions from this result.
                raise ProviderError("slack_incomplete_pagination")
            else:
                return
        raise ProviderError("source_inventory_limit")

    def scopes(self):
        result = self.call("auth.test")
        if result.get("team_id") != self.config.team_id:
            raise ProviderError("slack_workspace_mismatch", access_lost=True)
        url = urlsplit(result.get("url", ""))
        if (
            url.scheme != "https"
            or not url.hostname
            or not url.hostname.endswith(".slack.com")
            or url.username
            or url.password
        ):
            raise ProviderError("invalid_slack_workspace_url")
        self.workspace_url = result["url"].rstrip("/")
        return ["slack:" + channel for channel in self.config.channels]

    def access(self, scope_id):
        observed_at = datetime.now(timezone.utc)
        channel = scope_id.removeprefix("slack:")
        if channel not in self.config.channels:
            raise ProviderError("unknown_source_scope")
        info = self.call("conversations.info", channel=channel).get("channel", {})
        if info.get("id") != channel:
            raise ProviderError("slack_channel_mismatch", access_lost=True)
        members = []
        for page in self.pages("conversations.members", channel=channel, limit=200):
            if not isinstance(page.get("members"), list):
                raise ProviderError("invalid_slack_members")
            members.extend("slack-user:" + value for value in page["members"])
            if len(members) > 10000:
                raise ProviderError("source_membership_limit")
        return Scope(
            scope_id, "Slack · " + info.get("name", channel), sorted(set(members)), observed_at
        )

    def documents(self, scope_id):
        channel = scope_id.removeprefix("slack:")
        seen = set()

        def convert(message):
            timestamp = message.get("ts")
            if not isinstance(timestamp, str) or not re.fullmatch(r"[0-9]+\.[0-9]+", timestamp):
                raise ProviderError("invalid_slack_timestamp")
            if timestamp in seen:
                return None
            seen.add(timestamp)
            if len(seen) > self.config.max_messages:
                raise ProviderError("source_inventory_limit")
            text = message.get("text", "")
            if not isinstance(text, str):
                raise ProviderError("invalid_slack_message")
            # Preserve edits, author/time and file references without downloading
            # private attachment URLs or treating messages as verified instructions.
            metadata = {
                key: message[key]
                for key in ("user", "bot_id", "ts", "thread_ts", "subtype", "edited")
                if key in message
            }
            metadata.update(
                {"provider": "slack", "channel_id": channel, "team_id": self.config.team_id}
            )
            if message.get("files"):
                metadata["files"] = [
                    {key: f[key] for key in ("id", "name", "mimetype") if key in f}
                    for f in message["files"]
                ]
            revision = hashlib.sha256(
                json.dumps({"text": text, "metadata": metadata}, sort_keys=True).encode()
            ).hexdigest()
            return Document(
                f"{channel}:{timestamp}",
                revision,
                f"Slack message · {timestamp}",
                text,
                f"{self.workspace_url}/archives/{channel}/p{timestamp.replace('.', '')}",
                metadata=metadata,
            )

        for page in self.pages(
            "conversations.history", channel=channel, limit=self.config.page_size
        ):
            if not isinstance(page.get("messages"), list):
                raise ProviderError("invalid_slack_history")
            for message in page["messages"]:
                result = convert(message)
                if result:
                    yield result
                if self.config.include_threads and message.get("reply_count", 0) > 0:
                    for replies in self.pages(
                        "conversations.replies",
                        channel=channel,
                        ts=message["ts"],
                        limit=self.config.page_size,
                    ):
                        if not isinstance(replies.get("messages"), list):
                            raise ProviderError("invalid_slack_thread")
                        for reply in replies["messages"]:
                            result = convert(reply)
                            if result:
                                yield result
                        yield None
            yield None
