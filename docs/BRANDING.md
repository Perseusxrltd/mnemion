# Mnemion logo and brand assets

Mnemion uses the connected **M** already established in Studio, in the Perseus XR
palette: ink `#070b14`, gold `#c49a55`, bright gold `#e2b967` and ivory `#f2ead9`.
The single editable source is [`studio/branding/mnemion.svg`](../studio/branding/mnemion.svg).
Keep its geometry and three connection points consistent across products.

## Where the mark appears

- Studio welcome screen, workspace, documentation and legacy vault views use
  `mnemion.svg` through the shared `BrandMark` component.
- Windows executable, installer, uninstaller, shortcuts and tray use `icon.ico`,
  with real 16–256 px representations.
- macOS applications and installers use `icon.icns`, including Retina sizes.
  Its tray uses transparent monochrome template images at 1× and 2× so the menu
  bar can tint the mark correctly in either appearance.
- Linux application icons and shortcuts use `icon.png`; its tray has compact
  1× and 2× renders. Browser favicons use the vector and ICO; Apple touch icons
  use the 180 px render.
- The repository overview and historical `assets/mnemion_logo.png` path use the
  same mark. Old release files and historical screenshots retain their original
  artwork; new releases contain the current assets.
- The Perseus XR product page, homepage feature and product favicon use copies
  of these assets. The corporate Perseus XR logo remains a separate identity.

## Regeneration

From the repository root:

```sh
npm --prefix studio/branding ci
npm --prefix studio/branding run build
node studio/branding/verify.mjs
```

The generator renders the source locally with pinned Sharp, creates Windows ICO
and macOS ICNS containers, and records every output hash in
`studio/branding/assets.json`. It requires no paid service. Small raster sizes
use a slightly stronger stroke for readability; they keep the same geometry.
Commit the source, manifest and generated files together.

Web and desktop builds check these hashes automatically; desktop packaging also
checks the copied files in the built frontend. A stale icon fails the build.
For the website, copy `mnemion.svg`, `mnemion-symbol.svg`, `icon-180.png` and
`icon.png` from `studio/frontend/public` to its `public/media/brand` directory,
and `mnemion.svg` to `src/app/mnemion/icon.svg`. Inspect the product page and
homepage at desktop and mobile widths before deployment.

Keep the tile background for colour icons so gold remains readable against
light and dark OS surfaces. Use the symbol-only asset inside an existing dark
panel, and the template asset only for OS-controlled monochrome surfaces.
