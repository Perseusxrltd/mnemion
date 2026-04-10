#!/bin/bash
# Mnemion PreCompact Hook — thin wrapper calling Python CLI
# All logic lives in mnemion.hooks_cli for cross-harness extensibility
INPUT=$(cat)
echo "$INPUT" | python3 -m mnemion hook run --hook precompact --harness claude-code
