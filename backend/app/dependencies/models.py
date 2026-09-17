"""Data models and Enums for JakeAI Dependency Regression Automation (TEST-10)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DependencyCategory(StrEnum):
    """Authoritative dependency categories defined for JakeAI platform architecture."""

    FASTAPI = "fastapi"
    PYDANTIC = "pydantic"
    STARLETTE = "starlette"
    HTTPX = "httpx"
    LANGCHAIN = "langchain"
    LANGGRAPH = "langgraph"
    QDRANT_CLIENT = "qdrant_client"
    REDIS_CLIENT = "redis_client"
    PYJWT = "pyjwt"
    PROVIDER_SDKS = "provider_sdks"
    TEST_TOOLING = "test_tooling"


class FailureClass(StrEnum):
    """Classification of root cause failure patterns observed during dependency updates."""

    IMPORT_ERROR = "import_error"
    ATTRIBUTE_ERROR = "attribute_error"
    VALIDATION_ERROR = "validation_error"
    TYPE_ERROR = "type_error"
    SIGNATURE_MUTATION = "signature_mutation"
    DEPRECATION_REMOVAL = "deprecation_removal"
    SCHEMA_DRIFT = "schema_drift"
    HTTP_PROTOCOL_ERROR = "http_protocol_error"
    ASSERTION_FAILURE = "assertion_failure"
    TIMEOUT_OR_NETWORK = "timeout_or_network"
    UNKNOWN = "unknown"


class DependencySpec(BaseModel):
    """Metadata specification for a tracked dependency."""

    name: str = Field(description="Canonical normalized package name")
    category: DependencyCategory = Field(description="Subsystem architectural category")
    installed_version: str | None = Field(
        default=None, description="Currently installed package version in runtime"
    )
    declared_spec: str | None = Field(
        default=None,
        description="Declared constraint in requirements.txt or pyproject.toml",
    )
    is_direct: bool = Field(
        default=True,
        description="True if direct dependency, False if transitive (e.g. Starlette)",
    )
    affected_subsystems: list[str] = Field(
        default_factory=list,
        description="Subsystems vulnerable to changes in this package",
    )
    critical_test_paths: list[str] = Field(
        default_factory=list,
        description="Authoritative test paths exercising this dependency",
    )


class DependencyDiff(BaseModel):
    """Represents a detected version delta for a package."""

    dependency: str = Field(description="Package name")
    category: DependencyCategory = Field(
        description="Dependency architectural category"
    )
    old_version: str = Field(description="Baseline or previous version")
    new_version: str = Field(description="Candidate or new version")
    diff_type: str = Field(
        default="upgrade",
        description="Type of version delta: upgrade, downgrade, added, removed",
    )
    is_major_bump: bool = Field(
        default=False, description="True if major version changed"
    )
    is_minor_bump: bool = Field(
        default=False, description="True if minor version changed"
    )


class BreakageClassification(BaseModel):
    """Structured report of an empirical breakage caused by a dependency update.

    Conforms strictly to the TEST-10 specification:
    - dependency
    - old version
    - new version
    - failure
    - affected test
    - root cause
    - breaking API if confirmed
    - rollback/revert recommendation
    """

    dependency: str = Field(description="Target dependency package name")
    old_version: str = Field(description="Baseline version before update")
    new_version: str = Field(description="Candidate version introducing failure")
    failure: str = Field(
        description="Error message, exception name, or failure summary"
    )
    affected_test: str = Field(
        description="Specific test file or test method broken by update"
    )
    root_cause: str = Field(description="Detailed technical root cause analysis")
    breaking_api: str | None = Field(
        default=None,
        description="Confirmed breaking API signature or removed attribute if applicable",
    )
    rollback_recommendation: str = Field(
        description="Actionable rollback or revert recommendation with empirical evidence"
    )
    failure_class: FailureClass = Field(
        default=FailureClass.UNKNOWN, description="Classified failure taxonomy"
    )
    evidence: str | None = Field(
        default=None,
        description="Log snippet, stack trace or error context supporting diagnosis",
    )

    def to_formatted_dict(self) -> dict[str, Any]:
        """Output dict using specification keys."""
        return {
            "dependency": self.dependency,
            "old version": self.old_version,
            "new version": self.new_version,
            "failure": self.failure,
            "affected test": self.affected_test,
            "root cause": self.root_cause,
            "breaking API if confirmed": self.breaking_api or "None confirmed",
            "rollback/revert recommendation": self.rollback_recommendation,
        }


class ValidationSuiteResult(BaseModel):
    """Execution outcome of an automated validation suite."""

    suite_name: str = Field(
        description="Name of validation layer (lint, unit, contract, etc.)"
    )
    command: str = Field(description="Executed shell command")
    exit_code: int = Field(description="Process return code")
    passed: bool = Field(description="True if test suite passed cleanly")
    duration_seconds: float = Field(default=0.0, description="Duration in seconds")
    stdout_snippet: str = Field(default="", description="Relevant stdout snippet")
    stderr_snippet: str = Field(default="", description="Relevant stderr snippet")


class BreakageReport(BaseModel):
    """Full dependency regression and audit report."""

    timestamp: str = Field(description="ISO-8601 execution timestamp")
    base_ref: str = Field(
        default="main", description="Git base reference evaluated against"
    )
    target_ref: str = Field(
        default="HEAD", description="Target git reference or candidate state"
    )
    changed_dependencies: list[DependencyDiff] = Field(
        default_factory=list, description="All detected package diffs"
    )
    suite_results: list[ValidationSuiteResult] = Field(
        default_factory=list, description="Outcomes of validation suites"
    )
    breakages: list[BreakageClassification] = Field(
        default_factory=list, description="Identified breakages with root cause"
    )
    verdict: str = Field(
        default="PASS",
        description="Final verdict: PASS, REGRESSION_DETECTED, or NO_CHANGES",
    )

    @property
    def has_breakages(self) -> bool:
        return len(self.breakages) > 0 or any(not r.passed for r in self.suite_results)
