# Studio design system

From **4.0.8**, Studio follows the visual language of the
[Perseus XR product page](https://www.perseusxr.com/mnemion). The same local assets
and styles ship in Windows, macOS, Linux and web builds, including offline help.

## Shared identity

| Token | Value | Use |
| --- | --- | --- |
| Ink | `#02050d` | Application background |
| Soft ink | `#070b14` | Navigation and documentation library |
| Surface | `#0a0f19` | Content panels |
| Ivory | `#f2ead9` | Primary text |
| Muted ivory | `#b9b1a4` | Supporting text |
| Gold | `#c49a55` | Actions, dividers and selected navigation |
| Bright gold | `#e2b967` | Links, keyboard focus and active controls |
| Success | `#6ab28c` | Successful operations |
| Danger | `#e57972` | Errors and destructive actions |

Inter provides body and control text; Outfit provides headings and prominent
values. Latin and extended Latin font files are bundled, hash-inventoried and
licensed under the SIL Open Font License 1.1. Other scripts use the OS fallback.
Opening Studio does not contact a font provider. Provenance and original notices
are in `studio/frontend/public/fonts`; release notices also inventory both families.

The shared tokens live in `studio/frontend/src/index.css`. Tailwind's local-vault
aliases resolve to them. Workspace, insights, model settings, librarian, source
controls and the documentation library use the same palette. Keep distinctions
between multiple measured chart series: gold is an accent, not every data value.

## Interaction and layout

- Use restrained corners, hairline dividers and opaque dark surfaces. Avoid
  large blurred layers, continuous decorative animation and remote font loading.
- Group navigation into Memory, Intelligence and Workspace; retain explicit
  per-space role checks. Small windows expose the same navigation in a scrolling
  horizontal row. Desktop navigation scrolls independently of account controls.
- Preserve keyboard focus, the skip-to-content link, form labels and meaningful
  states. A selected route has both an accent and a structural indicator.
- Keep tables available alongside measured charts, descriptive series names,
  keyboard sample inspection and missing-data gaps. Color alone does not explain
  a result. Respect reduced-motion preferences.
- Keep documentation readable before connection and without a server. Its desktop
  library and article scroll independently; small layouts share a bounded scroll
  region. Relative documentation links resolve to the bundled library.
- Display the installed version from package metadata. The public product page
  separately follows published release metadata; neither needs a hardcoded
  patch label in a screen component.

## Validation when changing the interface

Build TypeScript and both web/Electron assets. Check connection, memory browsing,
creation, search, source controls, insights/evaluations, embedding/librarian
settings, Obsidian and documentation at desktop and narrow widths. Verify font
loading without external requests, keyboard navigation, reduced motion and
absence of layout overflow. Use isolated test data and report measured browser
and native results in the release validation record.

Visual consistency does not change memory formats, APIs, access rules or Obsidian
paths. The older local-vault routes keep their workflow and graph color categories.
