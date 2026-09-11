"""Versioned AI Quality Regression Baseline Store (TASK OPS-15).

Manages loading, saving, and querying versioned regression baselines
stored as source-controlled artifacts under app/evals/baselines/.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BaselineMetrics(BaseModel):
    """Canonical quality and performance baseline metrics contract."""

    version: str = "v1"
    created_at: float = Field(default_factory=time.time)
    avg_quality_score: float = Field(default=0.88, ge=0.0, le=1.0)
    min_pass_rate_pct: float = Field(default=95.0, ge=0.0, le=100.0)
    max_quality_regression: float = Field(default=0.05, ge=0.0, le=1.0)
    max_cost_regression: float = Field(default=0.10, ge=0.0, le=1.0)
    retrieval_mrr: float = Field(default=0.75, ge=0.0, le=1.0)
    groundedness_score: float = Field(default=0.88, ge=0.0, le=1.0)
    workload_baselines: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaselineStore:
    """Filesystem-backed manager for versioned AI quality baselines."""

    def __init__(self, baselines_dir: Path | None = None) -> None:
        if baselines_dir is None:
            self.baselines_dir = Path(__file__).resolve().parent / "baselines"
        else:
            self.baselines_dir = Path(baselines_dir)
        self.baselines_dir.mkdir(parents=True, exist_ok=True)

    def get_baseline_path(self, version: str = "v1") -> Path:
        """Return path to specific baseline JSON file."""
        return self.baselines_dir / f"baseline_{version}.json"

    def load_baseline(self, version: str = "v1") -> BaselineMetrics:
        """Load versioned baseline artifact or return default baseline if absent."""
        file_path = self.get_baseline_path(version)
        if not file_path.exists():
            logger.warning(
                "Baseline artifact '%s' not found at %s. Using default baseline metrics.",
                version,
                file_path,
            )
            return BaselineMetrics(version=version)

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            return BaselineMetrics(**data)

    def save_baseline(
        self, metrics: BaselineMetrics, version: str | None = None
    ) -> Path:
        """Persist baseline metrics artifact to disk."""
        target_version = version or metrics.version
        file_path = self.get_baseline_path(target_version)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(metrics.model_dump(), f, indent=2)
        logger.info("Saved baseline '%s' to %s", target_version, file_path)
        return file_path


default_baseline_store = BaselineStore()


def get_baseline_store() -> BaselineStore:
    """Singleton getter for BaselineStore."""
    return default_baseline_store
