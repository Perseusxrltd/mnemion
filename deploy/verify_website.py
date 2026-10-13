"""Verify the live product page against the published release, without credentials."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, build_opener

from .published_release import NoRedirects, ORIGIN, version

PRODUCT = "https://www.perseusxr.com/mnemion"
HOME = "https://www.perseusxr.com/"
MAX_BYTES = 2_000_000
GUIDES = ("updates", "deployment", "connectors", "agents", "README")


class Page(HTMLParser):
    """Exclude scripts, styles, templates and comments from visible-version proof."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.text: list[str] = []
        self.links: set[str] = set()

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template"}:
            self.hidden += 1
        if tag == "a" and not self.hidden:
            href = dict(attrs).get("href")
            if href:
                self.links.add(href)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.text.append(value)


def fetch_page(url: str) -> bytes:
    """Only the two canonical public pages; no environment token is consulted."""
    if url not in {PRODUCT, HOME}:
        raise ValueError("Only the canonical public product and home pages can be checked")
    opener = build_opener(NoRedirects())
    started = time.monotonic()
    request = Request(
        url, headers={"User-Agent": "Mnemion-public-page-verifier", "Accept-Encoding": "identity"}
    )
    try:
        response = opener.open(request, timeout=15)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        raise ValueError(f"The public page returned HTTP {status}") from None
    with response:
        if response.headers.get_content_type() != "text/html":
            raise ValueError("The public page did not return HTML")
        content = bytearray()
        while chunk := response.read(16384):
            content.extend(chunk)
            if len(content) > MAX_BYTES or time.monotonic() - started > 25:
                raise ValueError("The public page exceeded its transfer limit")
        return bytes(content)


def verify(published: dict, product: bytes, homepage: bytes) -> dict:
    """Require actual anchors for every available primary installer and guide."""
    tag = published["tag_name"]
    version(tag)
    if published.get("draft") is not False or published.get("prerelease") is not False:
        raise ValueError("Website verification requires a published stable release")
    for page in (product, homepage):
        if not isinstance(page, bytes) or len(page) > MAX_BYTES:
            raise ValueError("The public page exceeded its size limit")
    parsed, home = Page(), Page()
    parsed.feed(product.decode("utf-8"))
    home.feed(homepage.decode("utf-8"))
    release_version = tag.removeprefix("v")
    installer = re.compile(
        rf"Mnemion-Studio-{re.escape(release_version)}-(?:windows-(?:x64|arm64)\.exe|"
        r"macos-(?:x64|arm64)\.dmg|linux-(?:x86_64|arm64)\.AppImage)\Z"
    )
    names = sorted(
        asset["name"] for asset in published["assets"] if installer.fullmatch(asset["name"])
    )
    if not names or len(names) != len(set(names)):
        raise ValueError("No unambiguous primary installers were found in the published inventory")
    downloads = [f"{ORIGIN}/releases/download/{tag}/{name}" for name in names]
    notes = f"{ORIGIN}/releases/tag/{tag}"
    guides = [f"{ORIGIN}/blob/{tag}/docs/service/{name}.md" for name in GUIDES]
    checks = {
        "visible_current_version": bool(
            re.search(rf"(?<![\d.]){re.escape(release_version)}(?![\d.])", " ".join(parsed.text))
        ),
        "current_version_guides": all(link in parsed.links for link in guides),
        "checksum_link": f"{ORIGIN}/releases/download/{tag}/SHA256SUMS.txt" in parsed.links,
        "roadmap_tracks_main": f"{ORIGIN}/blob/main/docs/ROADMAP.md" in parsed.links,
        "homepage_product_link": any(
            urljoin(HOME, link).rstrip("/") == PRODUCT for link in home.links
        ),
        "current_release_notes": notes in parsed.links,
        "all_published_installer_links": all(link in parsed.links for link in downloads),
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise ValueError("The live product page is not current: " + ", ".join(failed))
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "version": release_version,
        "product_url": PRODUCT,
        "validation_method": "anonymous public HTML; script/style/template text excluded",
        **checks,
        "all_installer_links": downloads,
        "release_notes_url": notes,
        "current_guide_links": guides,
        "product_html_sha256": hashlib.sha256(product).hexdigest(),
        "website_code_or_deployment_changed": False,
        "new_visual_render_performed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("deploy/published-release.json"))
    parser.add_argument("--output", type=Path, default=Path("output/website-verification.json"))
    parser.add_argument("--attempts", type=int, choices=range(1, 7), default=4)
    args = parser.parse_args()
    manifest = args.manifest.read_bytes()
    if len(manifest) > 512 * 1024:
        raise ValueError("Published metadata exceeds its size limit")
    published = json.loads(manifest)
    for attempt in range(args.attempts):
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                product, homepage = pool.map(fetch_page, (PRODUCT, HOME))
            report = verify(published, product, homepage)
            break
        except (ValueError, OSError):
            if attempt + 1 == args.attempts:
                raise
            # Allow the public site's short cache to catch up after publication.
            time.sleep(10)
    if args.output.is_symlink():
        raise ValueError("The verification report must be a regular file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Verified live product page: {report['version']}, {len(report['all_installer_links'])} installer links"
    )


if __name__ == "__main__":
    main()
