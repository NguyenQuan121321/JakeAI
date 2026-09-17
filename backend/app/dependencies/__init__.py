"""JakeAI Dependency Regression Automation Package (TEST-10).

Provides dependency categorization, manifest auditing, diff detection,
breakage classification, and automated regression validation.
"""

from __future__ import annotations

from app.dependencies.models import (
    BreakageClassification,
    BreakageReport,
    DependencyCategory,
    DependencyDiff,
    DependencySpec,
    ValidationSuiteResult,
)

__all__ = [
    "BreakageClassification",
    "BreakageReport",
    "DependencyCategory",
    "DependencyDiff",
    "DependencySpec",
    "ValidationSuiteResult",
]
