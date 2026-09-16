#!/usr/bin/env python3
"""Wrapper delegating to root scripts/run_bruno_tests.py."""

import runpy
import sys
from pathlib import Path

ROOT_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent / "scripts" / "run_bruno_tests.py"
)

if __name__ == "__main__":
    if not ROOT_SCRIPT.is_file():
        print(f"[ERROR] Target script not found at {ROOT_SCRIPT}", file=sys.stderr)
        sys.exit(1)
    runpy.run_path(str(ROOT_SCRIPT), run_name="__main__")
