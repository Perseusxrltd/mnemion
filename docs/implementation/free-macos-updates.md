# Free macOS distribution and verified updates

Updated: **2026-10-10**. The implementation is on `main` and both Mac architectures
have passed the native and actual packaged Electron upgrade checks. Published
installer availability is shown on [the product page](https://www.perseusxr.com/mnemion).

Mnemion uses [Sparkle](https://sparkle-project.org/documentation/) **2.10.0**,
pinned to commit `eef1a539a373c1f1a320624b1130fc5de7b2e100` and a checked distribution
SHA-256. The upstream framework owns signature validation, extraction, replacement
and relaunch. Mnemion's small native control adapter communicates with Electron
through private pipes and waits for the app to authorize installation.

Mac compatibility does not require Apple membership. This pipeline uses ad-hoc
application signatures and a protected Ed25519 archive-signing key. It does not
provide Apple Developer ID identity or notarization. First installation may
require Privacy & Security approval, and managed devices may prohibit that.
Never disable Gatekeeper. See [installation and updates](../service/updates.md).

## Verified evidence

| Check | Commit and evidence | Result |
| --- | --- | --- |
| Unmodified upstream CLI, two disposable Cocoa apps | `44c48ce` · [run 38071829414](https://github.com/Perseusxrltd/mnemion/actions/runs/38071829414) | Intel and Apple silicon rejected invalid signatures and installed/relaunched a valid archive |
| Native Mnemion control adapter | `37bd0c9` · [run 38072833794](https://github.com/Perseusxrltd/mnemion/actions/runs/38072833794) | Verified updates waited for permission; cancellation prevented install on exit |
| Actual production package structure | `867e704` · [run 38073545786](https://github.com/Perseusxrltd/mnemion/actions/runs/38073545786) | Both native packages, embedded framework/helper, public key, license inventory and strict ad-hoc verification passed |
| Actual packaged Electron upgrade and release signing key | `873da44` · [run 38075042790](https://github.com/Perseusxrltd/mnemion/actions/runs/38075042790) | Both architectures verified the configured release signature; private fixture apps respected idle, active-transfer, draft and real-window focus guards, replaced and relaunched the target version |
| Native failure and recovery cases | `c088757` · [run 38075412900](https://github.com/Perseusxrltd/mnemion/actions/runs/38075412900) | Invalid signatures and interrupted downloads preserved the running app; oversized/older archives were rejected before download; parent disconnection and cancellation prevented installation; the following valid update installed and relaunched |

The packaged rehearsal repacks disposable copies with a test entry point and an
ephemeral signing key, retaining the actual compiled updater/controller. Idle time,
transfer state and a renderer draft are controlled fixture inputs. Native windows,
Sparkle, signature verification, the installer and relaunch are real. Production
bundles are not modified by the fixture. These tests do not simulate a power loss
during replacement or certify every managed-device first-install policy.

A later [26 October release-reliability checkpoint](../validation/2026-10-26-macos-release-reliability.md)
records two Intel Mac CI failures and scoped source corrections. Native
confirmation of those corrections remains pending; the earlier evidence above
retains its original scope.

## Boundaries and operation

Production feeds and archive URLs are fixed to the official repository, immutable
stable versions and the matching architecture. Downloads are limited to 1 GiB
and 20 minutes; a staged update expires after 24 hours. Cancellation uses Sparkle's
skip operation rather than dismissing into install-on-quit. The helper keeps its
run loop alive for two seconds after the cycle callback so asynchronous XPC
cleanup can finish. A normal Mac quit cancels the staged update.

`deploy/macos_sparkle.py` builds the verified helper and signs release archives.
`deploy/release.py` validates the two XML feeds and signatures before publication.
The installed public key is committed in `studio/electron/native/sparkle.json`;
the private key is an encrypted release secret with a separate private recovery
copy. The original Sparkle license and versioned inventory ship with the app.

For disposable native validation with Xcode Command Line Tools and Python 3.13:

```sh
python -m deploy.macos_update_bridge_probe --output /private/tmp/mnemion-update-check
```

Use a new private output directory. The workflow's optional `compare_upstream`
input repeats the original upstream CLI comparison. Production signing keys are
never used by those synthetic fixtures.
