"""Versioned Performance Baseline Store & Environment Discovery (TEST-09).

Manages:
- Loading and persisting versioned performance baselines under app/performance/baselines/
- Capturing deterministic execution environment (commit hash, Python version, OS, dependencies)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from app.performance.contracts import (
    EnvironmentMetadata,
    PerformanceBaseline,
    ScenarioBaseline,
)

logger = logging.getLogger(__name__)


def capture_environment_metadata(env_name: str = "local") -> EnvironmentMetadata:
    """Introspect current host environment, runtime versions, and dependency hash."""
    # 1. Capture Git Commit Hash
    commit_hash = os.environ.get("GITHUB_SHA") or "unknown"
    if commit_hash == "unknown":
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0:
                commit_hash = res.stdout.strip()[:12]
        except Exception:
            commit_hash = "unknown"

    # 2. Dependency Hash of requirements.txt
    dep_hash = "unknown"
    req_path = Path(__file__).resolve().parent.parent.parent / "requirements.txt"
    if req_path.exists():
        try:
            content = req_path.read_bytes()
            dep_hash = hashlib.sha256(content).hexdigest()[:16]
        except Exception:
            dep_hash = "unknown"

    return EnvironmentMetadata(
        commit=commit_hash,
        environment=env_name,
        python_version=sys.version.split()[0],
        os_name=platform.system(),
        platform_name=platform.platform(),
        cpu_count=os.cpu_count() or 1,
        dependencies_hash=dep_hash,
        recorded_at=time.time(),
    )


class PerformanceBaselineStore:
    """Filesystem-backed manager for versioned performance baselines."""

    def __init__(self, baselines_dir: Path | None = None) -> None:
        if baselines_dir is None:
            self.baselines_dir = Path(__file__).resolve().parent / "baselines"
        else:
            self.baselines_dir = Path(baselines_dir)
        self.baselines_dir.mkdir(parents=True, exist_ok=True)

    def get_baseline_path(self, version: str = "v1") -> Path:
        """Return path to specific baseline JSON file."""
        return self.baselines_dir / f"baseline_{version}.json"

    def baseline_exists(self, version: str = "v1") -> bool:
        """Check if baseline version exists on disk."""
        return self.get_baseline_path(version).exists()

    def load_baseline(self, version: str = "v1") -> PerformanceBaseline:
        """Load versioned baseline artifact or return default baseline if absent."""
        file_path = self.get_baseline_path(version)
        if not file_path.exists():
            logger.warning(
                "Performance baseline '%s' not found at %s. Creating empty baseline contract.",
                version,
                file_path,
            )
            return PerformanceBaseline(
                version=version,
                environment=capture_environment_metadata(),
            )

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            return PerformanceBaseline(**data)

    def save_baseline(
        self, baseline: PerformanceBaseline, version: str | None = None
    ) -> Path:
        """Persist baseline to disk."""
        v = version or baseline.version
        file_path = self.get_baseline_path(v)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(baseline.model_dump(), f, indent=2)
        logger.info("Saved performance baseline '%s' to %s", v, file_path)
        return file_path


default_baseline_store = PerformanceBaselineStore()


def get_performance_baseline_store() -> PerformanceBaselineStore:
    """Singleton getter for PerformanceBaselineStore."""
    return default_baseline_store
