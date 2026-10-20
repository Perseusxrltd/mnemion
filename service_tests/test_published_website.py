"""A release check must reject stale links and versions hidden only in scripts."""

import html
import json
import sys

import pytest

from deploy import verify_website as website


def fixture(release_version="4.1.6"):
    tag = "v" + release_version
    names = [
        f"Mnemion-Studio-{release_version}-{target}"
        for target in (
            "windows-x64.exe",
            "windows-arm64.exe",
            "macos-x64.dmg",
            "macos-arm64.dmg",
            "linux-x86_64.AppImage",
            "linux-arm64.AppImage",
        )
    ]
    manifest = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [{"name": name} for name in names],
    }
    links = [f"{website.ORIGIN}/releases/download/{tag}/{name}" for name in names]
    links.extend(f"{website.ORIGIN}/blob/{tag}/docs/service/{name}.md" for name in website.GUIDES)
    links.extend(
        (
            f"{website.ORIGIN}/releases/tag/{tag}",
            f"{website.ORIGIN}/releases/download/{tag}/SHA256SUMS.txt",
            f"{website.ORIGIN}/blob/main/docs/ROADMAP.md",
        )
    )
    product = (
        f"<main><p>Version {release_version}</p>"
        + "".join(f'<a href="{html.escape(link)}">Open</a>' for link in links)
        + "</main>"
    ).encode()
    return manifest, product, b'<a href="/mnemion">Mnemion</a>'


def test_live_page_report_covers_all_architectures_guides_and_homepage():
    report = website.verify(*fixture())
    assert report["version"] == "4.1.6"
    assert len(report["all_installer_links"]) == 6
    assert len(report["current_guide_links"]) == 5
    assert report["roadmap_tracks_main"] and report["current_release_notes"]
    assert not report["new_visual_render_performed"]


@pytest.mark.parametrize(
    "target",
    [
        "windows-x64.exe",
        "windows-arm64.exe",
        "macos-x64.dmg",
        "macos-arm64.dmg",
        "linux-x86_64.AppImage",
        "linux-arm64.AppImage",
        "SHA256SUMS.txt",
        "docs/service/agents.md",
        "docs/ROADMAP.md",
    ],
)
def test_missing_download_or_document_link_fails_even_when_its_name_is_present(target):
    manifest, product, home = fixture()
    product = product.replace(target.encode(), b"stale-" + target.encode())
    with pytest.raises(ValueError, match="not current"):
        website.verify(manifest, product, home)


@pytest.mark.parametrize("wrapper", ["script", "style", "template"])
def test_version_only_inside_nonvisible_content_is_not_a_pass(wrapper):
    manifest, product, home = fixture()
    product = product.replace(
        b"<p>Version 4.1.6</p>", f"<{wrapper}>4.1.6</{wrapper}><p>Version 4.1.5</p>".encode()
    )
    with pytest.raises(ValueError, match="visible_current_version"):
        website.verify(manifest, product, home)


def test_links_inside_templates_are_not_download_controls():
    manifest, product, home = fixture()
    with pytest.raises(ValueError, match="all_published_installer_links"):
        website.verify(manifest, b"<p>4.1.6</p><template>" + product + b"</template>", home)


def test_partial_publication_checks_available_installers_without_fabricating_others():
    manifest, product, home = fixture()
    manifest["assets"] = manifest["assets"][:1]
    assert len(website.verify(manifest, product, home)["all_installer_links"]) == 1


def test_private_preview_and_external_homepage_link_do_not_qualify():
    manifest, product, home = fixture()
    with pytest.raises(ValueError, match="published stable"):
        website.verify({**manifest, "draft": True}, product, home)
    with pytest.raises(ValueError, match="homepage_product_link"):
        website.verify(
            manifest, product, b'<a href="https://untrusted.example/mnemion">Mnemion</a>'
        )
    with pytest.raises(ValueError, match="canonical"):
        website.fetch_page("https://untrusted.example/")


def test_retry_after_cache_delay_writes_a_checked_receipt(tmp_path, monkeypatch):
    manifest, product, home = fixture()
    metadata, output = tmp_path / "manifest.json", tmp_path / "receipt.json"
    metadata.write_text(json.dumps(manifest))
    calls, delays = [], []

    def fetch(url):
        calls.append(url)
        if url == website.HOME:
            return home
        return (
            product.replace(b"Version 4.1.6", b"Version 4.1.5")
            if calls.count(website.PRODUCT) == 1
            else product
        )

    monkeypatch.setattr(website, "fetch_page", fetch)
    monkeypatch.setattr(website.time, "sleep", delays.append)
    monkeypatch.setattr(
        sys, "argv", ["verify-website", "--manifest", str(metadata), "--output", str(output)]
    )
    website.main()
    assert delays == [10]
    assert json.loads(output.read_text())["visible_current_version"] is True


def content_fixture():
    from pathlib import Path

    from deploy.website_content import build

    content = build(Path(__file__).resolve().parents[1])
    manifest, product, home = fixture(content["content"]["minimum_release"])
    digest = content["content_sha256"]
    body = content["content"]
    product = product.replace(b"<main>", f'<main data-mnemion-content="{digest}">'.encode())
    product += "".join(
        f"<p>{html.escape(text)}</p>"
        for text in [
            body["setup"]["steps"][0]["body"],
            body["downloads"]["platforms"]["macos"],
            body["features"][0]["title"],
        ]
    ).encode()
    home += f'<article data-mnemion-content="{digest}">{html.escape(body["project"]["outcome"])}</article>'.encode()
    lab = f'<article data-mnemion-content="{digest}">{html.escape(body["project"]["method"])}</article>'.encode()
    return manifest, product, home, content, lab


def test_git_owned_text_is_checked_on_all_three_public_surfaces():
    manifest, product, home, content, lab = content_fixture()
    result = website.verify(manifest, product, home, content=content, lab=lab)
    assert result["git_owned_product_text"]
    assert result["git_owned_homepage_text"] and result["git_owned_lab_notes_text"]
    assert json.loads(json.dumps(result))["release_notes_url"] == (
        f"{website.ORIGIN}/releases/tag/{manifest['tag_name']}"
    )


@pytest.mark.parametrize("surface", ["product", "home", "lab"])
def test_static_or_hidden_copy_cannot_satisfy_the_git_content_gate(surface):
    manifest, product, home, content, lab = content_fixture()
    pages = {"product": product, "home": home, "lab": lab}
    stale = pages[surface].replace(content["content_sha256"].encode(), b"0" * 64)
    pages[surface] = stale + b"<template>" + pages[surface] + b"</template>"
    with pytest.raises(ValueError, match="not current"):
        website.verify(manifest, pages["product"], pages["home"], content=content, lab=pages["lab"])
