# Git snapshot freshness — 14 October 2026

Source work for [4.3.2](../releases/4.3.2.md), addressing
[issue 37](https://github.com/Perseusxrltd/mnemion/issues/37).
Source checks and distribution acceptance are recorded separately; this file
does not claim that the original shared host has already installed this update.

Twenty-six focused checks passed in 23.25 seconds across connector sync,
managed connectors and the real HTTP runner. They cover:

- A real bare cache whose local `main` remains at the initial commit while a
  later fetch and completed inventory report the new commit through the API/SDK.
- The same checkpoint behavior for a local repository without a remote.
- Source deletion and unchanged-file revision stability across commits.
- An interrupted later inventory retaining the previous complete commit and date,
  with the failed-attempt state visible separately.
- Existing tenant, administrator and connector-runner authorization, competing
  sync requests, access failures and backup/recovery behavior.
- Managed receipts accepting the matching runtime/connector, retaining a dated
  previous result after a failed attempt, and clearing it after a successful
  older runtime without receipts. An inherited unrelated report destination is
  replaced with the connector's private destination.

The TypeScript client and Studio production builds passed, as did Python lint,
release metadata/schema preparation and whitespace checks. The UI addition is a
wrapping commit/date display in the existing source-status view; no new browser
flow was introduced or separately exercised.

The bare-cache test uses local fixture transport with actual Git operations;
it does not claim validation of a live provider's credentials or availability.
The new snapshot observation uses the existing complete-inventory checkpoint,
without a schema migration or changes to source memory identities. Public native
and automatic-update evidence is recorded by the release pipeline.
