"""Dependency manifest catalog and subsystem impact mapping for JakeAI (TEST-10)."""

from __future__ import annotations

import importlib.metadata
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from app.dependencies.models import DependencyCategory, DependencySpec

# Canonical package definitions mapped to architectural categories, subsystems, and test suites
KNOWN_DEPENDENCIES: dict[str, dict[str, Any]] = {
    "fastapi": {
        "category": DependencyCategory.FASTAPI,
        "is_direct": True,
        "affected_subsystems": [
            "Gateway & Routing",
            "API Perimeter",
            "OpenAPI Spec Generation",
            "HTTP Endpoints",
        ],
        "critical_test_paths": [
            "tests/contract/test_api_contract.py",
            "tests/integration/test_endpoints.py",
            "tests/integration/test_health.py",
            "tests/integration/test_r_func_00_api_behavior.py",
        ],
    },
    "uvicorn": {
        "category": DependencyCategory.FASTAPI,
        "is_direct": True,
        "affected_subsystems": [
            "ASGI Web Server",
            "Worker Lifecycle",
            "HTTP Transport",
        ],
        "critical_test_paths": [
            "tests/integration/test_health.py",
            "tests/integration/test_gateway.py",
        ],
    },
    "pydantic": {
        "category": DependencyCategory.PYDANTIC,
        "is_direct": True,
        "affected_subsystems": [
            "Domain Contracts",
            "Request/Response Validation",
            "Structured Output",
            "FinOps Accounting",
        ],
        "critical_test_paths": [
            "tests/contract/test_orchestration_contracts.py",
            "tests/contract/test_r_arch_04_contract_consistency.py",
            "tests/unit/test_structured_output.py",
            "tests/unit/test_finops_accounting.py",
            "tests/unit/test_r_logic_03_accounting.py",
        ],
    },
    "pydantic-settings": {
        "category": DependencyCategory.PYDANTIC,
        "is_direct": True,
        "affected_subsystems": [
            "Application Configuration",
            "Environment Variables Parsing",
            "Secrets Loading",
        ],
        "critical_test_paths": [
            "tests/unit/test_architecture_invariants.py",
            "tests/contract/test_api_contract.py",
        ],
    },
    "pydantic-core": {
        "category": DependencyCategory.PYDANTIC,
        "is_direct": False,
        "affected_subsystems": [
            "Rust Core Validation Engine",
            "Schema Deserialization",
        ],
        "critical_test_paths": [
            "tests/contract/test_orchestration_contracts.py",
            "tests/unit/test_structured_output.py",
        ],
    },
    "starlette": {
        "category": DependencyCategory.STARLETTE,
        "is_direct": False,
        "affected_subsystems": [
            "ASGI Middleware",
            "SSE Streaming (StreamingResponse)",
            "HTTP Request Pipeline",
        ],
        "critical_test_paths": [
            "tests/integration/test_gateway.py",
            "tests/unit/test_correlation_propagation.py",
            "tests/performance/test_performance_smoke.py",
        ],
    },
    "httpx": {
        "category": DependencyCategory.HTTPX,
        "is_direct": True,
        "affected_subsystems": [
            "HTTP Client Transport",
            "Async Provider Network I/O",
            "ASGI TestClient Fixtures",
        ],
        "critical_test_paths": [
            "tests/fixtures/client.py",
            "tests/integration/test_r_func_04_provider_behavior.py",
            "tests/contract/test_api_contract.py",
            "tests/integration/test_commercial_services.py",
        ],
    },
    "httpcore": {
        "category": DependencyCategory.HTTPX,
        "is_direct": False,
        "affected_subsystems": [
            "Low-level HTTP Socket Transport",
            "Connection Pooling",
        ],
        "critical_test_paths": [
            "tests/integration/test_r_func_04_provider_behavior.py",
        ],
    },
    "langchain": {
        "category": DependencyCategory.LANGCHAIN,
        "is_direct": True,
        "affected_subsystems": [
            "Prompt Formatting",
            "Document Chunking",
            "Message Schema Models",
        ],
        "critical_test_paths": [
            "tests/unit/test_rag.py",
            "tests/unit/test_rag_parsers.py",
            "tests/unit/test_rag_unified_envelope.py",
            "tests/evals/test_rag_regression.py",
        ],
    },
    "langchain-core": {
        "category": DependencyCategory.LANGCHAIN,
        "is_direct": True,
        "affected_subsystems": [
            "Runnable Protocol",
            "Base Messages",
            "Callback Handlers",
        ],
        "critical_test_paths": [
            "tests/unit/test_rag.py",
            "tests/unit/test_two_zone_compiler.py",
            "tests/evals/test_portfolio_benchmark.py",
        ],
    },
    "langchain-text-splitters": {
        "category": DependencyCategory.LANGCHAIN,
        "is_direct": True,
        "affected_subsystems": [
            "Recursive Character Splitter",
            "Token-Aware Text Chunking",
        ],
        "critical_test_paths": [
            "tests/unit/test_rag.py",
            "tests/unit/test_rag_parsers.py",
        ],
    },
    "langgraph": {
        "category": DependencyCategory.LANGGRAPH,
        "is_direct": True,
        "affected_subsystems": [
            "Multi-Agent State Graph",
            "Interrupt & Resume Bridge",
            "Execution Engine Adapter",
        ],
        "critical_test_paths": [
            "tests/unit/test_execution_engine_and_adapters.py",
            "tests/unit/test_multi_agent.py",
            "tests/integration/test_agent_platform.py",
            "tests/integration/test_resume_bridge.py",
            "tests/evals/test_eval_agent_automation.py",
        ],
    },
    "langgraph-checkpoint": {
        "category": DependencyCategory.LANGGRAPH,
        "is_direct": False,
        "affected_subsystems": ["Durable Checkpointer Protocol", "State Serialization"],
        "critical_test_paths": [
            "tests/unit/test_durable_checkpointing.py",
            "tests/integration/test_resume_bridge.py",
        ],
    },
    "langgraph-prebuilt": {
        "category": DependencyCategory.LANGGRAPH,
        "is_direct": False,
        "affected_subsystems": ["Prebuilt ToolNodes", "Supervisor Graph Helper"],
        "critical_test_paths": [
            "tests/unit/test_multi_agent.py",
        ],
    },
    "langgraph-sdk": {
        "category": DependencyCategory.LANGGRAPH,
        "is_direct": False,
        "affected_subsystems": ["Agent Protocol Client", "Run Dispatch"],
        "critical_test_paths": [
            "tests/integration/test_agent_platform.py",
        ],
    },
    "qdrant-client": {
        "category": DependencyCategory.QDRANT_CLIENT,
        "is_direct": True,
        "affected_subsystems": [
            "Qdrant Vector DB Client",
            "Dense Point Upsert",
            "Vector Similarity Search",
            "Tenant Filtering",
        ],
        "critical_test_paths": [
            "tests/unit/test_rag_embedding_and_points.py",
            "tests/unit/test_rag_hybrid_retrieval.py",
            "tests/integration/test_semantic_cache_real.py",
            "tests/security/test_rag_tenant_isolation.py",
            "tests/security/test_rag_tenant_isolation_hardened.py",
            "tests/performance/scenarios/qdrant_scenario.py",
        ],
    },
    "fastembed": {
        "category": DependencyCategory.QDRANT_CLIENT,
        "is_direct": True,
        "affected_subsystems": [
            "Local In-Process ONNX Embedding Engine",
            "Vector Dimension Invariants",
        ],
        "critical_test_paths": [
            "tests/unit/test_rag_embedding_and_points.py",
            "tests/integration/test_semantic_cache_real.py",
        ],
    },
    "pypdf": {
        "category": DependencyCategory.QDRANT_CLIENT,
        "is_direct": True,
        "affected_subsystems": ["PDF Ingestion Parser", "Text Extraction"],
        "critical_test_paths": [
            "tests/unit/test_rag_parsers.py",
        ],
    },
    "redis": {
        "category": DependencyCategory.REDIS_CLIENT,
        "is_direct": True,
        "affected_subsystems": [
            "Distributed Cache (Tier 1)",
            "FinOps Token Quota Ledger",
            "Durable Task Queue",
            "Agent Checkpointing",
        ],
        "critical_test_paths": [
            "tests/unit/test_durable_checkpointing.py",
            "tests/integration/test_async_worker.py",
            "tests/integration/test_r_func_03_cache_behavior.py",
            "tests/security/test_byok.py",
            "tests/performance/scenarios/redis_contention_scenario.py",
        ],
    },
    "pyjwt": {
        "category": DependencyCategory.PYJWT,
        "is_direct": True,
        "affected_subsystems": [
            "Perimeter JWT Verification",
            "HMAC/RSA Token Claims Decoding",
            "Tenant Context Injection",
        ],
        "critical_test_paths": [
            "tests/integration/test_gateway.py",
            "tests/contract/test_internal_mutual_auth.py",
            "tests/unit/test_correlation_propagation.py",
        ],
    },
    "cryptography": {
        "category": DependencyCategory.PYJWT,
        "is_direct": True,
        "affected_subsystems": [
            "AES-256-GCM BYOK Vault Encryption",
            "Sigstore Cosign OIDC Verification",
        ],
        "critical_test_paths": [
            "tests/security/test_byok.py",
            "tests/security/test_cosign_oidc_signing.py",
        ],
    },
    "tiktoken": {
        "category": DependencyCategory.PROVIDER_SDKS,
        "is_direct": True,
        "affected_subsystems": [
            "BPE Token Counting",
            "Prompt Budget Allocator",
            "FinOps Accurate Pricing",
        ],
        "critical_test_paths": [
            "tests/unit/test_rag_context_budget.py",
            "tests/performance/test_token_benchmark.py",
            "tests/unit/test_finops_accounting.py",
            "tests/unit/test_prompt_compression_live.py",
        ],
    },
    "pytest": {
        "category": DependencyCategory.TEST_TOOLING,
        "is_direct": True,
        "affected_subsystems": [
            "Test Execution Engine",
            "Fixture Dependency Injection",
            "Parametrization",
        ],
        "critical_test_paths": ["tests/conftest.py"],
    },
    "pytest-asyncio": {
        "category": DependencyCategory.TEST_TOOLING,
        "is_direct": True,
        "affected_subsystems": [
            "Async Event Loop Fixture Resolution",
            "Async Test Runner",
        ],
        "critical_test_paths": ["tests/conftest.py"],
    },
    "pytest-cov": {
        "category": DependencyCategory.TEST_TOOLING,
        "is_direct": True,
        "affected_subsystems": [
            "Branch & Line Coverage Instrumentation",
            "Coverage Floor Enforcement",
        ],
        "critical_test_paths": ["scripts/check_coverage_diff.py"],
    },
    "ruff": {
        "category": DependencyCategory.TEST_TOOLING,
        "is_direct": True,
        "affected_subsystems": ["Static Linting Gate", "Code Formatter Enforcement"],
        "critical_test_paths": [".ruff.toml"],
    },
    "mypy": {
        "category": DependencyCategory.TEST_TOOLING,
        "is_direct": True,
        "affected_subsystems": [
            "Static Type Checking Gate",
            "PEP 484/585/604 Type Conformance",
        ],
        "critical_test_paths": ["mypy.ini"],
    },
    "bandit": {
        "category": DependencyCategory.TEST_TOOLING,
        "is_direct": True,
        "affected_subsystems": [
            "DevSecOps SAST Scanner",
            "Security Invariant Verification",
        ],
        "critical_test_paths": ["pyproject.toml"],
    },
    "pip-audit": {
        "category": DependencyCategory.TEST_TOOLING,
        "is_direct": True,
        "affected_subsystems": [
            "CVE & Vulnerability Dependency Scanner",
            "Supply Chain Security",
        ],
        "critical_test_paths": ["requirements.txt"],
    },
    "pip-licenses": {
        "category": DependencyCategory.TEST_TOOLING,
        "is_direct": True,
        "affected_subsystems": [
            "Software License Compliance Gate (Copyleft Rejection)"
        ],
        "critical_test_paths": ["requirements.txt"],
    },
    "@usebruno/cli": {
        "category": DependencyCategory.TEST_TOOLING,
        "is_direct": True,
        "affected_subsystems": ["Bruno Automated API / E2E Smoke & Full Test Runner"],
        "critical_test_paths": ["scripts/run_bruno_tests.py", "Bruno/"],
    },
}


def normalize_package_name(name: str) -> str:
    """Normalize package name to lowercase with hyphens replacing underscores."""
    clean = re.split(r"[=<>\s~\[]", name)[0].strip().lower()
    return clean.replace("_", "-")


def resolve_category(package_name: str) -> DependencyCategory:
    """Resolve the DependencyCategory for a given package name."""
    norm = normalize_package_name(package_name)
    if norm in KNOWN_DEPENDENCIES:
        cat = KNOWN_DEPENDENCIES[norm]["category"]
        return cat if isinstance(cat, DependencyCategory) else DependencyCategory(cat)

    # Heuristic resolution based on package prefixes/keywords
    if "starlette" in norm:
        return DependencyCategory.STARLETTE
    if "fastapi" in norm or "uvicorn" in norm:
        return DependencyCategory.FASTAPI
    if "pydantic" in norm:
        return DependencyCategory.PYDANTIC
    if "httpx" in norm or "httpcore" in norm:
        return DependencyCategory.HTTPX
    if "langgraph" in norm:
        return DependencyCategory.LANGGRAPH
    if "langchain" in norm:
        return DependencyCategory.LANGCHAIN
    if "qdrant" in norm or "embed" in norm:
        return DependencyCategory.QDRANT_CLIENT
    if "redis" in norm:
        return DependencyCategory.REDIS_CLIENT
    if "jwt" in norm or "crypto" in norm:
        return DependencyCategory.PYJWT
    if any(
        k in norm for k in ["tiktoken", "openai", "anthropic", "gemini", "deepseek"]
    ):
        return DependencyCategory.PROVIDER_SDKS
    if any(
        k in norm
        for k in ["pytest", "ruff", "mypy", "bandit", "audit", "coverage", "bruno"]
    ):
        return DependencyCategory.TEST_TOOLING

    return DependencyCategory.TEST_TOOLING


def parse_requirements_file(file_path: Path) -> dict[str, str]:
    """Parse requirements.txt into a mapping of normalized_name -> pinned_version."""
    if not file_path.exists():
        return {}

    reqs: dict[str, str] = {}
    content = file_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Match e.g. fastapi==0.141.1 or uvicorn[standard]==0.52.4
        match = re.match(r"^([a-zA-Z0-9_\-\[\]]+)\s*==\s*([a-zA-Z0-9\.\-]+)", line)
        if match:
            raw_pkg, version = match.groups()
            norm = normalize_package_name(raw_pkg)
            reqs[norm] = version
    return reqs


def get_installed_version(package_name: str) -> str | None:
    """Query runtime environment via importlib.metadata for installed package version."""
    norm = normalize_package_name(package_name)
    # Try direct and common aliases
    for candidate in [norm, norm.replace("-", "_")]:
        try:
            return importlib.metadata.version(candidate)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def build_dependency_manifest(backend_dir: Path) -> dict[str, DependencySpec]:
    """Construct the complete authoritative DependencySpec manifest for JakeAI."""
    reqs_path = backend_dir / "requirements.txt"
    pinned_reqs = parse_requirements_file(reqs_path)

    manifest: dict[str, DependencySpec] = {}

    for name, meta in KNOWN_DEPENDENCIES.items():
        declared = pinned_reqs.get(name)
        installed = get_installed_version(name)

        manifest[name] = DependencySpec(
            name=name,
            category=meta["category"],
            installed_version=installed,
            declared_spec=declared,
            is_direct=meta.get("is_direct", True),
            affected_subsystems=meta.get("affected_subsystems", []),
            critical_test_paths=meta.get("critical_test_paths", []),
        )

    # Also capture any pinned packages in requirements.txt not explicitly enumerated
    for pkg_name, version in pinned_reqs.items():
        if pkg_name not in manifest:
            category = resolve_category(pkg_name)
            installed = get_installed_version(pkg_name)
            manifest[pkg_name] = DependencySpec(
                name=pkg_name,
                category=category,
                installed_version=installed,
                declared_spec=version,
                is_direct=True,
                affected_subsystems=["Core Platform Subsystems"],
                critical_test_paths=["tests/unit/"],
            )

    return manifest


def get_impacted_test_paths(packages: list[str]) -> list[str]:
    """Return deduplicated list of critical test paths affected by specified packages."""
    paths: set[str] = set()
    for pkg in packages:
        norm = normalize_package_name(pkg)
        if norm in KNOWN_DEPENDENCIES:
            paths.update(KNOWN_DEPENDENCIES[norm]["critical_test_paths"])
        else:
            paths.add("tests/unit/")
    return sorted(paths)
