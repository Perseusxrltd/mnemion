# Model providers in the desktop app

Source 4.33 adds **Setup & this device → Your model providers** for a workspace
hosted on this computer. The same controls are available from local setup before
sign-in. Check [release status](../RELEASE_STATUS.md) for published installers.

The existing E5 and BGE CPU embedding models remain available. You can add up to
eight embedding profiles and eight librarian profiles, using Ollama or an
OpenAI-compatible API. These can run on your computer, an organization server
or a cloud provider. No extra Python installation is needed for these controls.

## Add and use a model

1. Open **Your model providers**, then **Add embedding model** or
   **Add librarian model**.
2. Choose Ollama, a compatible local server, or a cloud/organization endpoint.
   A local external model server must already be installed and running.
3. Enter its complete API URL, exact model name and model revision. For
   embeddings, enter the dimensions from the model's documentation. A fixed
   model version or installed digest makes the selection reproducible.
4. Enter an API key if required. The advanced section supports an `api-key`
   header, custom CA certificates, response-model identity, input/output limits,
   embedding prefixes, timeouts and Ollama CPU/keep-alive settings.
5. Review the profile, then save. A running local host drains and restarts with
   its saved configuration. A stopped host stays stopped.
6. For embeddings, open **Embedding models** in the intended space, build and
   evaluate a candidate, then activate it. For the librarian, choose the profile
   in **Librarian**, set its schedule and daily call limit, and enable processing.

**Saving and inspecting profiles do not contact the model provider.** They do not
enable the librarian, select a new embedding generation or approve outbound
memory processing. Each space retains its own administrator approval. Cloud
providers may charge when processing is enabled; Mnemion itself remains free.

Changing a provider's mutable model without updating the recorded revision
cannot be detected reliably. Update that revision and rebuild/evaluate the
embedding candidate when model weights change. Librarian fingerprint changes
require its space settings to be reviewed again.

## Capacity and privacy

Desktop profiles use conservative UTF-8 byte budgets for input. They do not
download a tokenizer or model. Provider-reported output usage remains in model
tokens. Existing operator-file configuration can use separately pinned
tokenizers; desktop enrollment does not accept arbitrary environment references.

Embedding requests share one execution slot. Queue capacity uses the smallest
approved embedding-profile limit and the host's environment limit (16 by
default). A zero limit rejects an additional concurrent inference immediately;
saturated work does not become an unbounded queue or automatic billable retry.
Request, document and response limits still apply.

Ollama thread and keep-alive requests are sent to Ollama. Its memory allocation,
and other external servers' memory, belong to those servers; Mnemion's
cooperative RAM budget does not impose a hard limit on another program. A
desktop connecting to a team host needs no local model.

Keys are stored in `model-providers.json` under the private local-host data
folder. The file uses the owning OS account's permissions/Windows ACL; **it is
not an encrypted keychain record**. Keys never appear in model status, public
model choices, memory, Obsidian exports or profile fingerprints. They travel to
the host helper through its private input pipe, not command-line arguments.
Keep this private host folder out of source synchronization.

A blank replacement key retains the existing key. **Remove the saved API key**
clears it. Changing the endpoint, protocol or authentication header requires an
explicit new key or removal; a saved key cannot silently follow a new provider.
Non-loopback endpoints require HTTPS. URLs cannot contain embedded credentials,
fragments or arbitrary query parameters; the supported query is `api-version`.
TLS verification stays enabled, and redirects are not followed.

An OS-account operator can configure the local host while signed into a different
remote workspace. The panel names the local workspace it changes. A shared
workspace's administrator key alone does not grant access to its host computer
or install a model there. Environment-managed server profiles retain their
existing configuration path.

## Editing, removal and recovery

Edits use the current local workspace identity and settings revision. Concurrent
changes invalidate the draft before a host is stopped. Pending edits and private
operations block automatic app restarts.

Removing a profile removes its local saved key but preserves memories and
existing indexes. Processing requiring that profile is unavailable until a
usable profile is configured or another model is selected. Removing a librarian
profile does not acknowledge, apply or erase its earlier proposals.

Malformed model settings leave the built-in CPU profiles available. **Reset model
settings** preserves the exact damaged bytes privately before clearing custom
profiles. Files with unsafe ownership, links or unreadable permissions require
repair by their OS owner; reset does not weaken permissions.

Native database backups preserve memory and per-space model state, but do not
bundle this local operator file or its provider keys. After recovery, re-enroll
the exact approved profiles and review the destination/space settings before
resuming external processing. Preserve provider credentials separately through
your organization's usual credential recovery process. See
[native backups](native-backups.md) and [embedding recovery](embeddings.md).

## Local agent controls

The private desktop catalog adds `local.models`; read `status` first.
`info.settings.workspace_id` is the local host identity, distinct from a
service tenant ID. `info.model_access` supplies the current revision and masked
profile status. This is an OS-account operation, not a public memory API route.

Example private request; the placeholder is not a credential:

```json
{
  "request_id": "NEW-UUID",
  "action": "local.models",
  "expected_workspace_id": "LOCAL-WORKSPACE-UUID",
  "input": {
    "workspace_id": "LOCAL-WORKSPACE-UUID",
    "expected_revision": "not-configured",
    "action": "save",
    "provider": {
      "kind": "librarian",
      "profile": {
        "id": "local-librarian",
        "label": "Organization librarian",
        "protocol": "ollama",
        "endpoint": "http://127.0.0.1:11434/api/chat",
        "model": "YOUR-INSTALLED-MODEL",
        "revision": "YOUR-VERIFIED-MODEL-DIGEST"
      }
    }
  }
}
```

Embedding profiles also require `dimensions`. Optional write-only `api_key`,
`clear_api_key` and `ca_pem` accompany the provider, outside its public profile.
Requests are bounded by the desktop control's 16 KiB envelope; the model input
has a 15 KiB limit. Use current values from status, not a reused request ID.

For removal use `action: "remove"`, `kind` and `profile_id`; for damaged-file
repair use `action: "reset"` with the inspected revision. To configure a stopped
host without Studio, `mnemion-service local models --root <private-host-folder>`
reads the same input object from stdin. It acquires the local host lock and
cannot modify a host owned by another running process.

See [private desktop controls](desktop-operator.md), [embeddings](embeddings.md)
and the [librarian](librarian.md).
