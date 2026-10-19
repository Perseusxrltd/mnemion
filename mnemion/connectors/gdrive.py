"""Drive folders, text files and Workspace exports with per-file effective ACLs."""

import hashlib
from datetime import datetime, timezone
from urllib.parse import quote

from .http import ProviderHTTP
from .protocol import Document, Scope
from .providers import ProviderError, selected

FILE_FIELDS = "id,name,mimeType,version,modifiedTime,trashed,webViewLink,size,md5Checksum,capabilities(canDownload)"
EXPORTS = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.google-apps.presentation": "text/plain",
}
FOLDER = "application/vnd.google-apps.folder"


class DriveProvider:
    access_mode = "provider"

    def __init__(self, config, *, transport=None, sleep=None):
        self.config = config
        self.http = ProviderHTTP(
            "https://www.googleapis.com/drive/v3/",
            config.token,
            transport=transport,
            **({"sleep": sleep} if sleep else {}),
        )
        self.files = {}

    def close(self):
        self.http.close()

    def pages(self, path, **params):
        token = None
        seen = set()
        for _ in range(100000):
            result = self.http.get(path, {**params, **({"pageToken": token} if token else {})})
            if result.get("incompleteSearch"):
                raise ProviderError("drive_incomplete_inventory")
            yield result
            token = result.get("nextPageToken")
            if not token:
                return
            if token in seen:
                raise ProviderError("drive_repeated_cursor")
            seen.add(token)
        raise ProviderError("source_inventory_limit")

    def _file(self, identifier):
        value = self.http.get(
            "files/" + quote(identifier, safe=""),
            {"fields": FILE_FIELDS, "supportsAllDrives": "true"},
        )
        if value.get("id") != identifier:
            raise ProviderError("drive_file_mismatch")
        return value

    def scopes(self):
        self.files = {}
        queue = list(self.config.folder_ids)
        visited = set()
        for identifier in self.config.file_ids:
            self.files[identifier] = self._file(identifier)
        while queue:
            folder = queue.pop()
            if folder in visited:
                continue
            visited.add(folder)
            if len(visited) > self.config.max_files:
                raise ProviderError("source_inventory_limit")
            # A missing/inaccessible root cannot be mistaken for an empty vault.
            if self._file(folder).get("mimeType") != FOLDER:
                raise ProviderError("drive_root_is_not_a_folder")
            for page in self.pages(
                "files",
                q=f"'{folder}' in parents and trashed = false",
                fields="nextPageToken,incompleteSearch,files(" + FILE_FIELDS + ")",
                pageSize=1000,
                supportsAllDrives="true",
                includeItemsFromAllDrives="true",
            ):
                if not isinstance(page.get("files"), list):
                    raise ProviderError("invalid_drive_inventory")
                for value in page["files"]:
                    if value["mimeType"] == FOLDER:
                        if self.config.recursive:
                            queue.append(value["id"])
                    elif value["mimeType"] in EXPORTS or selected(self.config, value["name"]):
                        self.files[value["id"]] = value
                    if len(self.files) > self.config.max_files:
                        raise ProviderError("source_inventory_limit")
        return ["gdrive:" + identifier for identifier in sorted(self.files)]

    def access(self, scope_id):
        observed_at = datetime.now(timezone.utc)
        identifier = scope_id.removeprefix("gdrive:")
        if identifier not in self.files:
            raise ProviderError("unknown_source_scope")
        value = self._file(identifier)
        self.files[identifier] = value
        members = []
        for page in self.pages(
            "files/" + quote(identifier, safe="") + "/permissions",
            pageSize=100,
            fields="nextPageToken,permissions(id,type,role,deleted,expirationTime)",
            supportsAllDrives="true",
        ):
            if not isinstance(page.get("permissions"), list):
                raise ProviderError("invalid_drive_permissions")
            for permission in page["permissions"]:
                if permission.get("type") != "user" or permission.get("deleted"):
                    continue
                if permission.get("role") not in {
                    "owner",
                    "organizer",
                    "fileOrganizer",
                    "writer",
                    "commenter",
                    "reader",
                }:
                    continue
                expiry = permission.get("expirationTime")
                if expiry and datetime.fromisoformat(expiry.replace("Z", "+00:00")) <= datetime.now(
                    timezone.utc
                ):
                    continue
                members.append("google-user:" + permission["id"])
                if len(members) > 10000:
                    raise ProviderError("source_membership_limit")
        return Scope(
            scope_id, value["name"][:200] or "Drive file", sorted(set(members)), observed_at
        )

    def documents(self, scope_id):
        identifier = scope_id.removeprefix("gdrive:")
        value = self.files[identifier]
        if value.get("trashed"):
            return
        if value.get("capabilities", {}).get("canDownload") is False:
            raise ProviderError("drive_download_not_permitted", access_lost=True)
        if int(value.get("size", 0)) > self.config.max_file_bytes:
            raise ProviderError("source_too_large")
        mime = value["mimeType"]
        path = "files/" + quote(identifier, safe="")
        if mime in EXPORTS:
            data = self.http.get(
                path + "/export",
                {"mimeType": EXPORTS[mime]},
                binary=True,
                maximum=self.config.max_file_bytes,
            )
        elif mime.startswith("application/vnd.google-apps."):
            raise ProviderError("drive_export_type_not_supported")
        else:
            data = self.http.get(
                path,
                {"alt": "media", "supportsAllDrives": "true"},
                binary=True,
                maximum=self.config.max_file_bytes,
            )
            if (
                value.get("md5Checksum")
                and hashlib.md5(data, usedforsecurity=False).hexdigest() != value["md5Checksum"]
            ):
                raise ProviderError("drive_file_changed_during_read")
        after = self._file(identifier)
        if after.get("version") != value.get("version") or after.get("trashed"):
            raise ProviderError("drive_file_changed_during_read")
        if mime == "application/vnd.google-apps.spreadsheet":
            from .extract import spreadsheet

            text = spreadsheet(data)
        else:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ProviderError("source_is_not_utf8_text") from None
        if "\0" in text:
            raise ProviderError("source_contains_binary_data")
        from .providers import private_vault_content

        if private_vault_content(text):
            return
        metadata = {
            "provider": "gdrive",
            "file_id": identifier,
            "mime_type": mime,
            "modified_at": value.get("modifiedTime"),
            "original_sha256": hashlib.sha256(data).hexdigest(),
            "original_size_bytes": len(data),
            "export_mime_type": EXPORTS.get(mime),
            "provider_version": value.get("version"),
        }
        yield Document(
            identifier,
            hashlib.sha256(
                (str(value.get("version")) + ":" + hashlib.sha256(data).hexdigest()).encode()
            ).hexdigest(),
            value["name"],
            text,
            "https://drive.google.com/file/d/" + quote(identifier, safe="") + "/view",
            "text/markdown" if value["name"].lower().endswith(".md") else "text/plain",
            metadata,
            normalize_conversations=self.config.normalize_conversations
            and value["name"].lower().endswith((".json", ".jsonl")),
        )
