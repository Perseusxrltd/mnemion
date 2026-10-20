# Git-owned website documentation: implementation and local acceptance

Date: 20 October 2026.

The [documentation contract](../website/README.md) extends the existing release
metadata automation to Mnemion's product explanations, onboarding instructions,
platform captions, homepage feature and Lab Notes text. Git owns the reviewed
copy; the website retains its design, corporate identity, publication permissions,
contact and support configuration. Operating guides continue to reference the
published download version, while the roadmap follows `main`.

The canonical copy corrects the first step to offer personal sign-in/invitations,
independent scoped agent keys and **Create on this computer**. It distinguishes
the macOS 13+ desktop client from Apple-silicon local workspaces requiring macOS
14+. These corrections live in Mnemion's Git source rather than duplicate site
edits. App and hosted Studio documentation already bundle repository Markdown
from each exact release, including offline help; that mapping was verified.

## Checks completed

- Producer and public verifier: 32 focused cases passed across their affected
  groups (11 producer, 21 verifier), including malformed/oversized text, missing
  or external guides, unpublished release floors, metadata-only CI scope,
  visible text on all three surfaces, cache retries and JSON receipt output.
  Ruff checks and formatting passed. The updated workflow passed actionlint
  1.7.12 through the integrating agent's existing validation environment.
- Website: content/identity checks, lint, TypeScript and the Next.js production
  build passed. The 28 website cases passed across focused runs; the affected
  15-case release group was rerun after correcting an old fixture that assumed
  a permanent 4.0.0 bundled fallback. No dependency was added.
- The production dependency audit reported zero vulnerabilities. The full audit
  retains the previously documented `braces` advisory in the development-only
  lint dependency chain; this change did not alter that dependency tree.
- Styled product, homepage Mnemion feature and Lab Notes were checked at 320,
  390, 768 and 1440 pixels, without horizontal overflow. Desktop/mobile screenshots
  were inspected. The current logo, illustration, homepage motto and approved
  project visibility were preserved. Product/Lab Notes reported no browser
  console errors. The existing homepage Three.js hero hit this WSLG browser's
  SwiftShader WebGL limitation; its static fallback remained usable and visually
  intact. A delayed CSS-preload warning also appeared on that page.
- A local production server, with controlled responses at the canonical public
  Git URLs, rendered the expected source digest on all three surfaces. Published
  release 4.40.0 fixture data retained all six installer links and version-bound
  guides. The extended anonymous-HTML verifier generated a serializable receipt.
- On that same running build, a signed local push event advanced the page from
  the bundled copy to a different validated content digest after two requests.
  Subsequent malformed content, HTTP 503, oversized bodies and a future-release
  floor retained that newer cached value at HTTP 200. This tested persistence of
  a successful refresh, beyond merely falling back to the bundle. Unrelated
  branch/path events were ignored and a forged signature was rejected. The
  canonical copy was restored afterward.
- All 65 requirement IDs and statuses were preserved. The 20 October request is
  recorded under U09, with a cross-reference from W03; implementation alone does
  not close the broader documentation requirement. No paid service, model call,
  account, payment transaction or message was introduced.

The checked canonical content digest is
`e58095f2ddcbeb55772239cb7514bf085702fe5cf85c926361e28c4f19b1b462`.
Local evidence is retained privately under
`mnemion-completion/2026-10-20-website-git-content/`, including
`local-cache-acceptance.json` and `local-three-surface-receipt.json`. Browser
screenshots reside in the website review worktree's ignored `output/playwright/`.
No webhook credential is included in these reports.

## Live acceptance remains separate

These are implementation and local production-build results, not evidence that
the live website has received a Git-only content change. The existing repository
hook was read-only verified as release-only during this work. The integrating
agent will deploy the checked consumer first, add `push` to that same hook while
preserving its secret, then integrate the producer/workflow changes. A deliberate
canonical text change must subsequently appear on the live site with a changed
content digest and an unchanged website deployment before recording live
end-to-end acceptance.

The public workflow retains the published installer/update checks and adds the
expected Git content digest and visible text on all three pages. It permits a
bounded ten-minute cache propagation window in a fifteen-minute job and leaves
the deployed site untouched on verification failure. No app version, release
dispatch, website publication or webhook mutation was performed by this slice.
