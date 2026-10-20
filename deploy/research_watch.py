"""Free, bounded public metadata watch. Never run models or adopt dependencies."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 50
REPOSITORIES = (
    "MemPalace/mempalace",
    "mem0ai/mem0",
    "vectorize-io/hindsight",
    "getzep/graphiti",
    "letta-ai/letta-code",
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def sources(now: datetime) -> list[dict]:
    query = '(ti:"agent memory" OR ti:"long-term memory" OR ti:"memory consolidation") AND (cat:cs.AI OR cat:cs.CL OR cat:cs.LG)'
    return [
        {
            "id": "arxiv",
            "name": "arXiv agent-memory papers",
            "kind": "arxiv",
            "url": "https://export.arxiv.org/api/query?"
            + urlencode(
                {
                    "search_query": query,
                    "start": 0,
                    "max_results": 25,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
            ),
        },
        {
            "id": "crossref",
            "name": "Crossref recent memory research",
            "kind": "crossref",
            "url": "https://api.crossref.org/works?"
            + urlencode(
                {
                    "query": "large language model agent memory",
                    "filter": "from-pub-date:"
                    + (now - timedelta(days=60)).date().isoformat()
                    + ",until-pub-date:"
                    + now.date().isoformat(),
                    "rows": 25,
                    "sort": "relevance",
                    "order": "desc",
                }
            ),
        },
        *[
            {
                "id": "github:" + repo,
                "name": repo,
                "kind": "github",
                "repository": repo,
                "url": f"https://api.github.com/repos/{repo}/releases?per_page=5",
            }
            for repo in REPOSITORIES
        ],
        {
            "id": "jev",
            "name": "TypeSafe AI Jev model documentation",
            "kind": "jev",
            "url": "https://docs.typesafe.ai/models.md",
        },
    ]


def clean(value: str, limit: int = 300) -> str:
    if not isinstance(value, str):
        raise ValueError("Metadata text must be a string")
    return " ".join(html.unescape(value).split())[:limit]


def date(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Source timestamps require a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def fetch(source: dict) -> bytes:
    # Sources come exclusively from the trusted list above, never from feed text.
    request = Request(
        source["url"],
        headers={
            "User-Agent": "Mnemion-Research-Watch/1.0 (Perseus XR)",
            "Accept": "application/json, application/atom+xml, text/plain",
        },
    )
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        content = response.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("Public metadata exceeds the fetch bound")
    return content


def parse(source: dict, content: bytes) -> list[dict]:
    if len(content) > MAX_BYTES:
        raise ValueError("Public metadata exceeds the parse bound")
    kind, rows = source["kind"], []
    if kind == "arxiv":
        if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
            raise ValueError("XML declarations are not accepted")
        root = ET.fromstring(content)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        if root.tag != "{http://www.w3.org/2005/Atom}feed":
            raise ValueError("Expected an Atom feed")
        for entry in root.findall("a:entry", ns)[:25]:
            url = urlsplit(entry.findtext("a:id", default="", namespaces=ns))
            match = re.fullmatch(r"/abs/(\d{4}\.\d{4,5})(v\d+)?", url.path)
            if url.hostname != "arxiv.org" or not match:
                raise ValueError("Unexpected arXiv identifier")
            rows.append(
                {
                    "id": "arxiv:" + match[1],
                    "title": clean(entry.findtext("a:title", "", ns)),
                    "url": "https://arxiv.org/abs/" + match[1],
                    "published": date(entry.findtext("a:published", "", ns)),
                    "updated": date(entry.findtext("a:updated", "", ns)),
                    "revision": match[2] or "",
                    "kind": "paper",
                    "reviewed": False,
                }
            )
    elif kind == "crossref":
        entries = json.loads(content)["message"]["items"]
        if not isinstance(entries, list):
            raise ValueError("Expected Crossref items")
        for entry in entries[:25]:
            title = clean((entry.get("title") or [""])[0])
            if not re.search(r"\b(?:agent|LLM|language model)\b", title, re.I) or not re.search(
                r"memor", title, re.I
            ):
                continue
            identifier = entry["DOI"]
            if not re.fullmatch(r"10\.\d{4,9}/[^\s<>\"']{1,250}", identifier):
                raise ValueError("Unexpected DOI")
            parts = entry["published"]["date-parts"][0]
            published = datetime(*((parts + [1, 1])[:3]), tzinfo=timezone.utc).isoformat(
                timespec="seconds"
            )
            rows.append(
                {
                    "id": "doi:" + identifier.lower(),
                    "title": title,
                    "url": "https://doi.org/" + quote(identifier, safe="/"),
                    "published": published,
                    "updated": published,
                    "revision": "",
                    "kind": "paper",
                    "reviewed": False,
                }
            )
    elif kind == "github":
        entries = json.loads(content)
        if not isinstance(entries, list):
            raise ValueError("Expected GitHub release metadata")
        for entry in entries[:5]:
            if entry.get("draft") or not entry.get("published_at"):
                continue
            identifier = entry["id"]
            if type(identifier) is not int or identifier <= 0:
                raise ValueError("Unexpected release identifier")
            tag = clean(entry["tag_name"], 100)
            rows.append(
                {
                    "id": source["id"] + ":" + str(identifier),
                    "title": clean(entry.get("name") or tag),
                    "url": "https://github.com/"
                    + source["repository"]
                    + "/releases/tag/"
                    + quote(tag, safe=""),
                    "published": date(entry["published_at"]),
                    "updated": date(entry["published_at"]),
                    "revision": tag,
                    "kind": "preview release" if entry.get("prerelease") else "release",
                    "reviewed": False,
                }
            )
    elif kind == "jev":
        models = sorted(set(re.findall(r"\bjev-\d+\.\d+\.\d+\b", content.decode("utf-8"))))
        if not models or len(models) > 25:
            raise ValueError("No bounded Jev model inventory found")
        rows = [
            {
                "id": "typesafe:" + model,
                "title": model + " mentioned in model documentation",
                "url": "https://docs.typesafe.ai/models",
                "published": None,
                "updated": None,
                "revision": model,
                "kind": "model documentation",
                "reviewed": False,
            }
            for model in models
        ]
    else:
        raise ValueError("Unsupported trusted feed")
    # Revisions of the same paper are one candidate, retaining the newer observation.
    unique = {}
    for row in rows:
        before = unique.get(row["id"])
        if before is None or (row["updated"] or "") > (before["updated"] or ""):
            unique[row["id"]] = row
    return list(unique.values())


def collect(previous: dict, *, now: datetime | None = None, getter=fetch) -> dict:
    now = now or datetime.now(timezone.utc)
    at = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    old = {row["id"]: row for row in previous.get("sources", [])}

    def inspect(source):
        before = old.get(source["id"], {})
        row = {
            **source,
            "attempted_at": at,
            "status": "unavailable",
            "last_success_at": before.get("last_success_at"),
            "content_sha256": before.get("content_sha256"),
            "items": before.get("items", []),
        }
        try:
            content = getter(source)
            entries = parse(source, content)
            retained = {item["id"]: item for item in row["items"]}
            for item in entries:
                prior = retained.get(item["id"], {})
                retained[item["id"]] = {
                    **item,
                    "discovered_at": prior.get("discovered_at", at),
                    "last_seen_at": at,
                }
            row.update(
                status="ok",
                last_success_at=at,
                content_sha256=hashlib.sha256(content).hexdigest(),
                items=sorted(
                    retained.values(),
                    key=lambda item: item.get("updated") or item.get("last_seen_at", ""),
                    reverse=True,
                )[:MAX_ITEMS],
            )
        except HTTPError as error:
            row["error"] = "HTTP " + str(error.code)
        except (URLError, TimeoutError, OSError):
            row["error"] = "Network unavailable or timed out"
        except (ValueError, KeyError, IndexError, OverflowError, TypeError, ET.ParseError):
            row["error"] = "Metadata format changed or exceeded its bound"
        return row

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(inspect, sources(now)))
    return {
        "schema": 1,
        "checked_at": at,
        "model_calls": 0,
        "dependency_changes": 0,
        "maximum_retained_per_source": MAX_ITEMS,
        "sources": results,
    }


def escaped(value: str) -> str:
    return (
        re.sub(r"([\\`*_{}\[\]()#+.!|])", r"\\\1", clean(value))
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def markdown(snapshot: dict) -> str:
    lines = [
        "# Scientific papers and memory-tool watch",
        "",
        "Automatically checked **" + snapshot["checked_at"] + "**. These are public metadata",
        "candidates, not reviewed recommendations, benchmark results or Mnemion features.",
        "No model calls, purchases, account creation or dependency upgrades occur.",
        "",
        "The weekly watch retains at most 50 candidates per source. It preserves the last",
        "successful catalog when a feed fails. It is a selective watch, not a systematic",
        "literature review. Source-document content is never executed or installed.",
        "",
        "See the [layered librarian study](2026-10-20-layered-librarian.md) for the current",
        "research interpretation, Jev assessment and required adoption measurements.",
        "",
        "| Source | Latest fetch | Last successful fetch | Retained candidates |",
        "| --- | --- | --- | --- |",
    ]
    for source in snapshot["sources"]:
        status = "OK" if source["status"] == "ok" else source.get("error", "Unavailable")
        lines.append(
            f"| {escaped(source['name'])} | {escaped(status)} | {source['last_success_at'] or 'None recorded'} | {len(source['items'])} |"
        )
    for source in snapshot["sources"]:
        lines.extend(["", "## " + escaped(source["name"]), ""])
        if not source["items"]:
            lines.append("No candidates are currently recorded from this bounded feed.")
        for item in source["items"]:
            published = (
                item["published"][:10]
                if item.get("published")
                else "Date not stated by this inventory"
            )
            lines.append(
                f"- [{escaped(item['title'])}]({item['url']}) — {published}; {item['kind']}; unreviewed."
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="Update only the generated watch catalog and guide"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root / "deploy/research-watch.json"
    previous = json.loads(path.read_text()) if path.exists() else {}
    snapshot = collect(previous)
    if args.write:
        path.write_text(json.dumps(snapshot, indent=2) + "\n")
        (root / "docs/research/RESEARCH_WATCH.md").write_text(markdown(snapshot))
    print(
        json.dumps(
            {
                "checked_at": snapshot["checked_at"],
                "sources": len(snapshot["sources"]),
                "succeeded": sum(row["status"] == "ok" for row in snapshot["sources"]),
                "candidates": sum(len(row["items"]) for row in snapshot["sources"]),
                "model_calls": 0,
                "dependency_changes": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
