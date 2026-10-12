# Navigation and desktop update readiness — 2026-10-12

The persistent sidebar **Memory space** selector was handled as an unsaved edit
by the desktop preload. Its element survives navigation between workspace views,
so selecting a space could block update readiness for the rest of that session.
Version 4.1.4 marks this navigation control safe for updates without changing
the preload's draft, transfer or restart policy.

At **14:32:54 UTC**, a real browser reproduced the problem using the compiled
production preload and the built 4.1.3 product interface. A synthetic read-only
desktop transport supplied two accessible spaces. Readiness started true,
became false after selecting the other space, and stayed false after moving to
Setup. No external request, memory write or browser error occurred. This checks
the real DOM and preload behavior; it does not impersonate native OS storage or
claim an installed update.

At **14:44:25 UTC**, the rebuilt 4.1.4 interface and production preload passed
the same browser scenario: readiness stayed true after the space and view
changes, became false while a real memory editor held an unsaved draft, and
returned to true after closing that disposable editor. No external request,
memory write or browser error occurred. See the [before/after receipts](2026-10-12-navigation-update-safety.json).

The installed local-workspace probe now exercises the actual packaged selector,
verifies that an unsaved memory still blocks update readiness, and closes only
its disposable editor to confirm readiness returns. The Electron test suite,
Studio build and version-consistency checks passed. All six native installed
gates then passed the new selector and draft scenarios. Version 4.1.4 is
published; see the [release and actual-session record](2026-10-12-navigation-update-release.md).

The actual Windows installation automatically downloaded the verified 4.1.2
installer during its normal scheduled check. Its saved independent administrator
still authenticated to the shared 4.1.1 server. The 25-minute observation did
not complete an automatic restart; subsequent investigation included opening
the actual app and navigation attempts. That incomplete live observation is
separate from the deterministic browser reproduction and the passing public
update rehearsals. No installer, update policy, clock, draft or credential was
modified to manufacture a passing live result.
