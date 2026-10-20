# Desktop cloud source acceptance — 20 October 2026

Source candidate: 4.34.0. Installer publication is a separate gate in
[release status](../RELEASE_STATUS.md).

## Completed

- **15 Python cases passed** across cloud credentials/capture and existing
  desktop source state/capture. Actual PostgreSQL and the HTTP memory service
  verified both adapters, dedicated application identity, provider membership
  removal, denial of forged mappings, and reports without keys or memory bodies.
- Google assertion signatures, read-only scope, fixed HTTPS audience, bounded
  expiry and token renewal were checked. Malformed, oversized and retargeted
  credentials were rejected. Parsing a key makes no provider request.
- **8 Node controller cases passed**, including separate provider/application
  ciphertext, reopening, retaining either existing key, private helper input,
  Slack-workspace retarget refusal and draining removal.
- Existing folder/conversation wire records retain their previous shape.
  Public source status excludes both credential ciphertexts.
- The actual Linux Electron source app saved both providers through the form,
  captured their selected fixture records into a real HTTP/PostgreSQL workspace,
  recovered from an invalid Google key and read a valid key through its file
  chooser. No local database was installed on the contributing device.
- Real OS storage (`gnome_libsecret`) protected both credentials. Private agent
  commands reverified the saved providers without resupplying either key. App
  removal while signed out and private-agent removal left no saved sources.
- The walkthrough found a false unsaved-edit flag on the connection selector.
  Selecting a connection now permits updates after source settings are saved;
  actual source drafts still block updates. The narrow layout had no horizontal
  page overflow. The completed run observed zero renderer console errors using
  Electron's current console-event interface.
- Frontend and Electron production builds passed. The source walkthrough uses
  the real private helper and service with a disposable upstream HTTP fixture;
  it does not send keys to a real cloud provider.

Provider HTTP responses in these checks are controlled fixtures. No customer
Slack/Google account, paid service or real provider credential was used.

## Remaining acceptance

Native release jobs are pending at this checkpoint. Customer-account sign-in,
provider-app enrollment, interactive
Google OAuth and Slack token rotation remain separate scope. Passing the local
fixtures does not certify those integrations or mark the complete source
onboarding requirement shipped.
