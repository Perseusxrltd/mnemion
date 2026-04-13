#!/usr/bin/env python3
"""Example: mine a project folder into the Anaktoron."""

import sys

project_dir = sys.argv[1] if len(sys.argv) > 1 else "~/projects/my_app"
print("Step 1: Initialize rooms from folder structure")
print(f"  mnemion init {project_dir}")
print("\nStep 2: Mine everything")
print(f"  mnemion mine {project_dir}")
print("\nStep 3: Search")
print("  mnemion search 'why did we choose this approach'")
