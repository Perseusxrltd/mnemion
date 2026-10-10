# How to Use Mnemion Hooks (Auto-Save)

> **Compatibility reference, reviewed 2026-10-10.** Legacy hook tutorial below describe the optional v3-compatible backend. For shared-platform v1, use the [current service guide](../docs/service/capture.md) and `main`. These historical commands and claims are not the default service architecture or current performance measurements.

Mnemion hooks act as an "Auto-Save" feature. They help your AI keep a permanent memory without you needing to run manual commands.

### 1. What are these hooks?
* **Save Hook** (`mnemion_save_hook.sh`): Saves new facts and decisions every 15 messages.
* **PreCompact Hook** (`mnemion_precompact_hook.sh`): Saves your context right before the AI's memory window fills up.

### 2. Setup for Claude Code
Add this to your configuration file to enable automatic background saving:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "", 
        "hooks": [{"type": "command", "command": "./hooks/mnemion_save_hook.sh"}]
      }
    ],
    "PreCompact": [
      {
        "matcher": "", 
        "hooks": [{"type": "command", "command": "./hooks/mnemion_precompact_hook.sh"}]
      }
    ]
  }
}