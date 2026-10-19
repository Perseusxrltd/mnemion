"""Additive Git tree updates, without checkout, local hooks or force-push."""

from __future__ import annotations

from collections import defaultdict
import io
import re
import time

from .. import local_state
from .config import Destination
from .format import (
    JournalCatalog,
    JournalEntry,
    JournalError,
    MAX_FILE_BYTES,
    parse_catalog,
    parse_file,
)
from .privacy import scan
from .process import program_environment, run
from .spool import Spool

OID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def environment():
    # Keep the OS identity, certificate/proxy configuration and credential
    # manager. Inherited Git command/config overrides cannot change this job.
    result = program_environment()
    result.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            "GIT_AUTHOR_NAME": "Mnemion",
            "GIT_AUTHOR_EMAIL": "journal@mnemion.invalid",
            "GIT_COMMITTER_NAME": "Mnemion",
            "GIT_COMMITTER_EMAIL": "journal@mnemion.invalid",
        }
    )
    return result


class GitJournal:
    def __init__(self, destination: Destination, *, cancel=None):
        self.destination = destination
        self.cancel = cancel
        self.spool = Spool(destination)
        self.repository = self.spool.root / "repository.git"
        self.hooks = local_state.directory(self.spool.root / "disabled-hooks")
        self.remote = destination.remote or str(destination.local_repository)
        self.ref = "refs/heads/" + destination.branch
        self.env = environment()
        self.control = local_state.directory(self.spool.root / "publisher-control")
        with local_state.lock(self.control):
            if not self.repository.exists():
                local_state.directory(self.repository, exist_ok=False)
                self._git("init", "--bare", str(self.repository), in_repository=False)
            local_state._regular(self.repository, directory=True)
            if self._git("rev-parse", "--is-bare-repository").strip() != b"true":
                raise JournalError("journal_cache_not_bare")
        if destination.local_repository is not None:
            path = destination.local_repository
            if (
                path.is_symlink()
                or not path.is_dir()
                or getattr(path.lstat(), "st_file_attributes", 0) & 0x400
            ):
                raise JournalError("invalid_local_journal_repository")
            if (
                self._git(
                    "-C", str(path), "rev-parse", "--is-bare-repository", in_repository=False
                ).strip()
                != b"true"
            ):
                raise JournalError("journal_destination_not_bare")

    def _git(self, *args, input=None, maximum=1024 * 1024, accepted=(0,), in_repository=True):
        options = [
            "git",
            "--literal-pathspecs",
            "-c",
            "core.hooksPath=" + str(self.hooks),
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.https.allow=always",
            "-c",
            "credential.interactive=never",
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
        ]
        if self.destination.local_repository is not None:
            options += ["-c", "protocol.file.allow=always"]
        if in_repository:
            options += ["-C", str(self.repository)]
        code, output = run(
            options + list(args),
            input=input,
            env=self.env,
            timeout=60,
            maximum=maximum,
            cancel=self.cancel,
        )
        if code not in accepted:
            raise JournalError("journal_git_command_failed")
        return output

    @staticmethod
    def _oid(value: bytes) -> str:
        try:
            result = value.decode("ascii").strip()
        except UnicodeError:
            raise JournalError("invalid_journal_git_object") from None
        if not OID.fullmatch(result):
            raise JournalError("invalid_journal_git_object")
        return result

    def _fetch(self):
        head = self._git(
            "ls-remote",
            "--exit-code",
            "--heads",
            "--",
            self.remote,
            self.ref,
            accepted=(0, 2),
            maximum=1024,
        )
        if not head.strip():
            if (self.spool.root / "publication.json").exists():
                raise JournalError("journal_remote_branch_disappeared")
            return None
        fields = head.decode("ascii").strip().split()
        if len(fields) != 2 or fields[1] != self.ref:
            raise JournalError("invalid_journal_remote_ref")
        self._oid(fields[0].encode())
        self._git(
            "fetch",
            "--depth=1",
            "--no-tags",
            "--no-recurse-submodules",
            "--",
            self.remote,
            self.ref,
        )
        return self._oid(self._git("rev-parse", "--verify", "FETCH_HEAD^{commit}", maximum=128))

    def _blob(self, head, path):
        if head is None:
            return None
        row = self._git("ls-tree", "-z", head, "--", path, maximum=4096)
        if not row:
            return None
        try:
            attributes, filename = row.rstrip(b"\0").split(b"\t", 1)
            mode, kind, oid = attributes.split()
            if mode != b"100644" or kind != b"blob" or filename.decode("utf-8") != path:
                raise ValueError
            object_id = self._oid(oid)
            size = int(self._git("cat-file", "-s", object_id, maximum=128))
        except (ValueError, UnicodeError):
            raise JournalError("journal_path_is_not_a_regular_file") from None
        if size > MAX_FILE_BYTES:
            raise JournalError("journal_file_too_large")
        return self._git("cat-file", "blob", object_id, maximum=MAX_FILE_BYTES)

    def _append(self, head, path, additions):
        active = self._blob(head, path)
        archive_path = (
            self.destination.prefix + "/_archive/" + path[len(self.destination.prefix) + 1 :]
        )
        archived = self._blob(head, archive_path)
        target = archive_path if archived is not None else path
        existing = (archived if archived is not None else active) or b""
        known = {}
        for content in (archived, active):
            for entry in parse_file(io.BytesIO(content or b"")):
                self._scope(entry)
                if path != self.destination.prefix + "/" + entry.relative_path:
                    raise JournalError("journal_record_path_mismatch")
                digest = entry.digest
                if str(entry.id) in known and known[str(entry.id)] != digest:
                    raise JournalError("journal_entry_conflict")
                known[str(entry.id)] = digest
        extra = bytearray()
        added = 0
        for entry in sorted(additions, key=lambda e: (e.ts, str(e.id))):
            previous = known.get(str(entry.id))
            if previous:
                if previous != entry.digest:
                    raise JournalError("journal_entry_conflict")
                continue
            line = entry.line()
            if len(existing) + len(extra) + len(line) > MAX_FILE_BYTES:
                raise JournalError("journal_file_too_large")
            extra.extend(line)
            known[str(entry.id)] = entry.digest
            added += 1
        return (existing + extra if extra else None), added, target

    def _catalog(self, head):
        path = self.destination.prefix + "/catalog.json"
        value = self._blob(head, path)
        if value is None:
            if head and self._git(
                "ls-tree", "-r", "--name-only", head, "--", self.destination.prefix
            ):
                raise JournalError("journal_catalog_missing")
            return JournalCatalog(
                tenant_id=self.destination.tenant_id, space_id=self.destination.space_id, records=0
            )
        catalog = parse_catalog(value)
        if (catalog.tenant_id, catalog.space_id) != (
            self.destination.tenant_id,
            self.destination.space_id,
        ):
            raise JournalError("journal_scope_mismatch")
        return catalog

    def _protect_previous(self, head):
        previous = self.spool.root / "publication.json"
        if not previous.exists() or head is None:
            return
        old = local_state.read(previous)["commit"]
        if not isinstance(old, str) or not OID.fullmatch(old):
            raise JournalError("invalid_journal_publication_receipt")
        changes = self._git(
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-z",
            old,
            head,
            "--",
            self.destination.prefix,
        ).split(b"\0")
        if changes[-1:] == [b""]:
            changes.pop()
        if len(changes) % 2:
            raise JournalError("invalid_journal_git_diff")
        for action, filename in zip(changes[::2], changes[1::2], strict=True):
            if action == b"A":
                continue
            if action not in {b"M", b"D"}:
                raise JournalError("journal_remote_history_changed")
            path = filename.decode("utf-8")
            before = self._blob(old, path)
            after = self._blob(head, path)
            if path == self.destination.prefix + "/catalog.json" and before and after:
                prior, current = parse_catalog(before), parse_catalog(after)
                if prior.namespace != current.namespace or current.records < prior.records:
                    raise JournalError("journal_remote_history_changed")
                continue
            if after is None and path.startswith(self.destination.prefix + "/"):
                archived = (
                    self.destination.prefix
                    + "/_archive/"
                    + path[len(self.destination.prefix) + 1 :]
                )
                after = self._blob(head, archived)
                if (
                    before is not None
                    and after is not None
                    and (after.startswith(before) or b"\n" + before in after)
                ):
                    continue  # An intact move may append to an older archive.
            if before is None or after is None or not after.startswith(before):
                raise JournalError("journal_remote_history_changed")

    def _scope(self, entry):
        if (entry.tenant_id, entry.space_id) != (
            self.destination.tenant_id,
            self.destination.space_id,
        ):
            raise JournalError("journal_scope_mismatch")

    def publish(self, entries: list[JournalEntry], *, before_push=None):
        """A returned commit is acknowledged upstream; local receipts alone are not."""
        started = time.monotonic()
        total = sum(len(entry.line()) for entry in entries)
        if (
            not entries
            or len(entries) > self.destination.max_batch_entries
            or total > self.destination.max_batch_bytes
        ):
            raise JournalError("journal_batch_limit")
        groups = defaultdict(list)
        for entry in entries:
            self._scope(entry)
            scan(
                entry,
                personal_data=self.destination.personal_data_scan,
                scanner=self.destination.scanner,
            )
            groups[self.destination.prefix + "/" + entry.relative_path].append(entry)
        # A slow network push must not lock the local receipt path used by saves.
        with local_state.lock(self.control):
            for attempt in range(3):
                head = self._fetch()
                self._protect_previous(head)
                catalog = self._catalog(head)
                if head:
                    self._git("read-tree", head)
                else:
                    self._git("read-tree", "--empty")
                updates = []
                added_records = 0
                for path, additions in sorted(groups.items()):
                    content, added, target = self._append(head, path, additions)
                    added_records += added
                    if content is not None:
                        oid = self._oid(
                            self._git("hash-object", "-w", "--stdin", input=content, maximum=128)
                        )
                        updates.append(f"100644 {oid}\t{target}\n")
                if added_records:
                    catalog = JournalCatalog(
                        tenant_id=catalog.tenant_id,
                        space_id=catalog.space_id,
                        records=catalog.records + added_records,
                    )
                    oid = self._oid(
                        self._git(
                            "hash-object", "-w", "--stdin", input=catalog.encoded(), maximum=128
                        )
                    )
                    updates.append(f"100644 {oid}\t{self.destination.prefix}/catalog.json\n")
                if before_push is not None:
                    before_push()
                if not updates:
                    commit = head
                else:
                    self._git("update-index", "--index-info", input="".join(updates).encode())
                    tree = self._oid(self._git("write-tree", maximum=128))
                    commit = self._oid(
                        self._git(
                            "commit-tree",
                            tree,
                            *(["-p", head] if head else []),
                            "-m",
                            "Append Mnemion memory journal",
                            maximum=128,
                        )
                    )
                    output = self._git(
                        "push",
                        "--porcelain",
                        "--no-verify",
                        "--",
                        self.remote,
                        commit + ":" + self.ref,
                        accepted=(0, 1),
                    )
                    if b"[rejected]" in output:
                        if attempt < 2 and (
                            b"fetch first" in output or b"non-fast-forward" in output
                        ):
                            continue
                        raise JournalError("journal_push_rejected")
                    # Porcelain must identify successful creation/update/up-to-date.
                    if not any(
                        line.startswith((b"*\t", b" \t", b"=\t")) and self.ref.encode() in line
                        for line in output.splitlines()
                    ):
                        raise JournalError("journal_push_not_confirmed")
                report = {
                    "commit": commit,
                    "entries": len(entries),
                    "bytes": total,
                    "attempts": attempt + 1,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "destination_fingerprint": self.destination.fingerprint,
                }
                local_state.write(self.spool.root / "publication.json", report)
                return report
        raise JournalError("journal_push_rejected")
