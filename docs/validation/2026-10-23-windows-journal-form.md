# Windows journal registration form timing

**23 October 2026 source correction checkpoint.** The first frozen 4.46.1
attempt used source
[`42aa7e0c0bbcad6f4d9bd8901c5695a9b264f95e`](https://github.com/Perseusxrltd/mnemion/commit/42aa7e0c0bbcad6f4d9bd8901c5695a9b264f95e)
in [run 39913638457](https://github.com/Perseusxrltd/mnemion/actions/runs/39913638457).
Its [Windows x64 job 120283946139](https://github.com/Perseusxrltd/mnemion/actions/runs/39913638457/job/120283946139)
failed installed hosting at **06:57:45 UTC**, after ordinary workspace creation,
memory save and semantic recall had completed. It could not find the journal
repository URL field. The original bounded diagnostic reported selector
`unknown` and route `other`; the installed-hosting receipt records `passed: false`.
The original job log and evidence archive remain preserved privately.

The [journal setup component](../../studio/frontend/src/workspace/JournalHostSetup.tsx)
cleared its draft when host/workspace identity arrived. That reset used a passive
React effect: a newly enabled **Register a repository** button could be clicked
before the effect ran, after which the reset removed the opened form.
The correction uses `useLayoutEffect` for the same identity-bound reset, so it
completes before exposing the controls for interaction.

An actual Chromium browser probe used synthetic data and a `MutationObserver`
to click the first enabled registration button. The original browser receipt is
dated **07:07:41 UTC**. The observed before/after results were:

| Source | Click observed | Form present after click | Registration button still present |
| --- | --- | --- | --- |
| Before correction | `true` | `false` | `true` |
| After layout-effect correction | `true` | `true` | `false` |

This reproduces the form timing failure and verifies the corrected source
behavior in the browser. It does not qualify a rebuilt Windows installer,
repository publication or a live host update.

The [native producer](../../studio/electron/local-hosting-probe.ts) and
[receipt reader](../../studio/electron/scripts/smoke-installed-hosting.mjs)
also recognize the fixed selector `.ws-journal-host input[type="url"]` and
the fixed `journal` route. Their diagnostic allowlists still exclude input
values, page text, arbitrary routes and query strings. This improves future
failure classification; it does not rewrite the original `unknown` receipt.

The [completed browser receipt](2026-10-23-windows-journal-form.json) also
records that refreshing the same host retains the entered repository and review
checkbox, while a different host identity clears both the draft and its approval.
The frontend TypeScript/production build and Electron TypeScript build passed.
Only synthetic state was used; no repository or host operation was performed.

A new frozen native attempt has not yet been dispatched at this checkpoint.
The original failed attempt is retained;
no retry, native release pass, publication or actual deployment acceptance is
claimed by this source/browser correction. The
[managed-startup evidence](2026-10-23-managed-startup.md) and
[4.46.0 live rollback](2026-10-23-4460-live-rollout.md) retain their separate scope.
