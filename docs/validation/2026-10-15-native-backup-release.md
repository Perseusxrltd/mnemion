# Published native backup and local-agent release

Version **4.6.0** is published. It includes the guided encrypted backups and
independent recovery from the unpublished 4.5.0 batch, Windows ownership and
metadata corrections, and 19 private local desktop operations for agents.

The immutable source `d7b4465b422cf73c51e9131d3eb85423c0ab5ee2` passed all **32**
[release jobs](https://github.com/Perseusxrltd/mnemion/actions/runs/38680133894),
including installed workspace, backup/recovery and update gates on Windows,
macOS and Linux for x64 and ARM64. Windows ARM uses the documented x64 service
engine. Earlier failed candidates remain frozen and are not the public source.

[Independent uploaded-artifact verification and publication](https://github.com/Perseusxrltd/mnemion/actions/runs/38684052387)
passed. The [live website verification](https://github.com/Perseusxrltd/mnemion/actions/runs/38684155620)
also passed, updating the [Perseus XR product page](https://www.perseusxr.com/mnemion)
without a manual website edit. The separate
[public automatic-upgrade run](https://github.com/Perseusxrltd/mnemion/actions/runs/38684157633)
passed on all six targets. [Per-version status](releases/4.6.0-status.json)
retains the observed delivery evidence.

The [backup guide](../service/native-backups.md) and
[operator guide](../service/desktop-operator.md) describe the workflows and their
authority boundaries. Configurable retention is a separate 4.7.0 addition.
Provider delivery verification, independent host takeover, company recovery
policy and broader deployment coverage remain open. Publication does not mark
the broader F08 or A09 requirements fully complete.
