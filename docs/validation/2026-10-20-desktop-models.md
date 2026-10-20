# Desktop model enrollment — 20 October 2026

Published 4.33 adds private local-host enrollment for embedding and librarian
profiles. Source `8d5e2f76d62f0a26e950e6516f6c06cf72a4e93a` passed
[all six native targets](https://github.com/Perseusxrltd/mnemion/actions/runs/39382743155)
and [independent artifact verification](https://github.com/Perseusxrltd/mnemion/actions/runs/39387307827).
The [website follow-up](https://github.com/Perseusxrltd/mnemion/actions/runs/39387465064)
also passed. Subsequent public update results are recorded in
[release status](../RELEASE_STATUS.md).

## Completed checks

- Ten focused Python cases passed: private credential retention/removal,
  identity and revision conflicts, credential retargeting refusal, preserved
  malformed files, safe built-in fallback, bounded CLI validation and existing
  external configuration.
- Real loopback HTTP exercised both Ollama and OpenAI-compatible embedding and
  librarian requests with the enrolled private key. Enrollment and registry
  construction issued no provider requests.
- A real PostgreSQL/service case exposed the enrolled choices while preserving
  disabled librarian processing and explicit per-space cloud approval. No
  public model-enrollment route was introduced.
- A real concurrent HTTP case verified that an enrolled zero-queue limit rejects
  excess work before it reaches the provider and leaves the first request intact.
  That case plus the existing HTTP and inference groups passed 55 cases.
- All 57 desktop local-workspace controller cases passed, including model input
  and credential-output checks and drain/save/confirmed-restart behavior. The
  provider confirmation accepts the server's explicit null tokenizer defaults.
- Frontend, hosted Studio and Electron production builds passed.
- The actual Linux Electron source-app walkthrough passed with a disposable
  native PostgreSQL 18.6 host and pinned CPU model cache. It saved an embedding
  profile through the form, refused a local agent restart while that form had
  unsaved edits, and preserved the workspace identity through real restarts.
- The same walkthrough exercised the installed probe's two-provider enrollment,
  private credential persistence, registered API choices, disabled librarian,
  setup display and removal. It also removed the UI-created profile while signed
  out. No provider inference ran, and no fixture profiles remained.
- The 500-pixel layout had no horizontal overflow. The final browser run had
  zero console errors. The walkthrough caught a browser pattern incompatibility;
  model IDs and agent connection names now accept hyphens with valid HTML
  patterns. Native probing retries only the pre-mutation refusal caused by a
  background app read starting between its safety checks; pending edits still
  prevent the operation.

This local walkthrough uses the production desktop build with a source Python
engine wrapper. It does not substitute for the six packaged native gates,
which subsequently passed before publication.

The checks use disposable workspaces, synthetic provider endpoints and fixture
keys. They do not call a paid model, install external model software, change the
user's real workspace profiles or certify a vendor's model quality.

The installed backup/resume gate includes `verifyNativeModels`: enrollment of
both kinds, private credential persistence, actual host restarts, registered
public choices, displayed setup and removal, with zero inference during enrollment.
Its result passed on each supported target before publication.
