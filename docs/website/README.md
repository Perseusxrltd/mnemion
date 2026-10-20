# One Git source for Mnemion documentation

Maintain Mnemion documentation in this repository. The app, public product page,
homepage feature and Lab Notes entry consume reviewed Git sources; routine text
or release updates require no duplicate website edit or deployment.

| Surface | Authoritative source | Update boundary |
| --- | --- | --- |
| App and hosted Studio documentation | `docs/**/*.md`, root `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, and `studio/README.md` | Bundled from the exact source of each app/service release; remains readable offline |
| Website product explanations, setup text, platform captions, homepage and Lab Notes Mnemion text | [content.json](content.json), validated by [content.schema.json](content.schema.json) | Reviewed `main` content, after its minimum required release is published |
| Downloads, visible version, checksums and release notes | Verified published GitHub release and `deploy/published-release.json` | Published stable release only; each offered architecture keeps its complete update assets |
| Website operating-guide links | Markdown in the downloaded release's Git tag | The published version users actually download |
| Website roadmap link | [Product roadmap](../ROADMAP.md) on `main` | Includes planning between releases |

`studio/frontend/src/workspace/Documentation.tsx` loads repository Markdown as
lazy local assets. The Vite build checks its essential guides and current release
notes before packaging. This is the same documentation library in Electron and
hosted Studio; no separate CMS, model call or online key is needed to read it.

## Updating public text

Edit `docs/website/content.json` and any affected Markdown guides in the same
reviewed Git change. The JSON contains text and repository guide paths only.
It cannot change CSS, insert HTML, choose a payment recipient, grant project
publication permission or supply download URLs. Keep claims limited to accepted
behavior. Set `minimum_release` to the first published version that supports all
operating instructions in the text. Newer release requirements hold publication
of that text while the previous public copy remains available.

Run `python -m deploy.website_content` in the locked development environment to
validate schema, text bounds, guide paths and the release floor. `--write` updates
the generated `deploy/website-content.json` only after validation. Ordinarily the
existing [website synchronization workflow](../../.github/workflows/website-release.yml)
does this automatically on documentation pushes to `main`, release publication or
edits, and its six-hour reconciliation schedule. It commits only the generated
release/content manifests; unchanged results produce no new commit.

The website reads the generated content from the fixed public Git URL. It checks
the deployed schema, content digest and release floor before caching a result.
Requests have a 3.5-second deadline and a 64 KiB content limit. Validated content
revalidates every five minutes. Refresh failures throw inside the persistent
cache, retaining its last good value. A cold cache can use the validated snapshot
generated from this repository during the last website build.

The website's `sync:mnemion`/`prebuild` script refreshes those generated snapshots
from Git and retains them when Git is unavailable. A local checkout may be
provided with `MNEMION_WEBSITE_SOURCE` for a reviewed build or isolated test.
It validates both content and release metadata before replacing snapshots and
does not downgrade an existing newer release snapshot.

### Download guidance and compatible rollout

The optional `downloads.guidance` group owns the mobile, processor-selection,
download-availability and change-computer explanations. When present, all eleven
fields are required, each with at most 400 characters of plain text; URLs, URI
schemes, HTML and control characters are rejected. Download destinations, the
current GitHub releases link, architecture eligibility and UI layout remain in
the website code. Availability text must not promise a release order or refer
users to an old initial-release note.

This is an additive schema-1 field, not an app feature or version change. Deploy
the reviewed website consumer and its updated schema **before** publishing a
manifest with guidance. That consumer must accept older schema-1 feeds without
the group and use its validated bundled guidance until the Git source includes
it. An older consumer rejects the unfamiliar group and retains its existing
validated content; it does not learn the new fields automatically. Once the
consumer is deployed, merge the canonical content/schema change and let the
normal workflow publish and verify it. Subsequent guidance edits need only this
repository. The existing `minimum_release` floor remains tied to the product
instructions, not the date of the website consumer deployment.

## Automatic invalidation and verification

The existing signed repository webhook accepts release events and normal
documentation/content pushes to `main`. The repository hook is subscribed to
both **release** and **push**. Its existing HMAC secret stays in GitHub's hook
configuration and the website's private environment. An event only invalidates
fixed cache tags/paths; its payload cannot provide rendered content or URLs.
Other branches, deleted branches and unrelated changes do not invalidate the
documentation cache. A missed event still converges through normal revalidation.

The website synchronization workflow independently checks visible version,
all offered installers, matching guide/notes/checksum links, the `main` roadmap,
and the expected Git-owned product, homepage and Lab Notes text. It records
the content digest alongside release evidence. It returns immediately when
current and otherwise allows a bounded ten-minute cache-propagation window
inside a fifteen-minute job. A failed check reports failure; it cannot replace
or deploy the live website.

The initial rollout passed live acceptance on 20 October 2026: after the reviewed
consumer was deployed and the existing hook gained `push`, a distinct canonical
Git change reached all three live surfaces without another website deployment.
Normal documentation changes now need only this repository. Git deployment of
the corporate website stays disabled; code/layout releases still use its existing
production project.

A new content schema or layout still requires a reviewed website code update.
Brand assets, corporate identity, contact delivery and payment configuration keep
their existing controlled sources. Automation does not turn incomplete product
requirements into shipped features or change the free-product/no-spending policy.

See the [implementation and live acceptance record](../validation/2026-10-20-git-owned-website-content.md)
for separate local cache-failure checks and the successful production Git refresh.
