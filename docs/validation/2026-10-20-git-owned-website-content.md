# Git-owned website documentation: implementation and live acceptance

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

## Local implementation checks

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

The locally checked canonical content digest was
`e58095f2ddcbeb55772239cb7514bf085702fe5cf85c926361e28c4f19b1b462`.
Local evidence is retained privately under
`mnemion-completion/2026-10-20-website-git-content/`, including
`local-cache-acceptance.json` and `local-three-surface-receipt.json`. Browser
screenshots reside in the website review worktree's ignored `output/playwright/`.
No webhook credential is included in these reports.

## Live Git-only acceptance passed

The local checks above preceded a separate live acceptance on 20 October at
14:25 UTC. The reviewed website consumer (`19cb27f`) was deployed first. The
existing hook, initially release-only, was extended to **release and push** by
changing only its event subscription; its secret was neither read nor replaced.
Mnemion commit `fca12c7db24d5defecf3e8cb583ee208aac13296` then published different
canonical text through Git. Its actual push delivery returned HTTP 200 with
`accepted`, `revalidated` and `content` all true.

The live product page displayed the new paragraph:

> Read guides for the version you download and follow the latest roadmap. The same help is available inside the app, including offline.

The product page, homepage and Lab Notes all advanced from the locally checked
digest above to
`7fb9a810a102acbe0a6b230953bdafb5a2224edca81a28a44fe0e34e34513639`.
Production deployment `dpl_Eh4X1VezfcWWiKv1LFtUWAajkP8X` stayed identical before
and after that Git push. This proves a real Git-only content refresh without
another website deployment, beyond matching an unchanged bundled fallback.

[Website workflow 39438860803](https://github.com/Perseusxrltd/mnemion/actions/runs/39438860803)
passed independently and retained its public verification receipt. Live checks
confirmed all six 4.40.0 installer links, published-version operating guides,
checksums, release notes and the `main` roadmap. The committed website release
fallback remained **4.39.0**; dynamic release sources served **4.40.0**. Both the
`www` product URL and apex redirect worked, and legal/privacy pages returned
HTTP 200. Contact/payment code remained unchanged; no new delivery or payment
test was performed. The protected preview toolbar was blocked by the unchanged
CSP, without a product-page error.

The same private evidence directory contains `live-end-to-end.json`,
`live-before-git-push.json`, `live-git-only-receipt.json`,
`preview-three-surface-receipt.json`, `hook-subscription.json`,
`verified-hook-push.json`, both production deployment inspections and
`github-workflow-proof/website-verification.json`. The local fixture results
remain separate evidence for invalid-response and cache-retention behavior;
production was not fault-injected.

The public workflow retains the published installer/update checks and adds the
expected Git content digest and visible text on all three pages. It permits a
bounded ten-minute cache propagation window in a fifteen-minute job and leaves
the deployed site untouched on verification failure. This documentation update
does not change an app version or close the broader U09 requirement; affected
guides, roadmap claims and release evidence still require engineering review.
