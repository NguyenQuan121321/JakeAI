"""Root CLI wrapper for JakeAI Performance Regression Automation (TEST-09)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
target_script = backend_dir / "scripts" / "run_performance_benchmark.py"

if __name__ == "__main__":
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(backend_dir)
        if not existing_pythonpath
        else f"{backend_dir}{os.pathsep}{existing_pythonpath}"
    )

    cmd = [sys.executable, str(target_script)] + sys.argv[1:]
    result = subprocess.run(cmd, cwd=backend_dir, env=env)
    sys.exit(result.returncode)
