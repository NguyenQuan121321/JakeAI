"""Unit tests for JakeAI Dependency Categories & Manifest (TEST-10 / DEP-001 / CAT-129)."""

from __future__ import annotations

from pathlib import Path

import pytest
from packaging.version import Version

from app.dependencies.manifest import (
    KNOWN_DEPENDENCIES,
    build_dependency_manifest,
    get_impacted_test_paths,
    normalize_package_name,
    parse_requirements_file,
    resolve_category,
)
from app.dependencies.models import DependencyCategory

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


@pytest.mark.unit
class TestDependencyCategories:
    """Validate completeness and correctness of all 11 required dependency categories."""

    def test_all_11_required_categories_defined(self) -> None:
        """Verify that all 11 required categories exist in DependencyCategory enum."""
        required_categories = {
            "fastapi",
            "pydantic",
            "starlette",
            "httpx",
            "langchain",
            "langgraph",
            "qdrant_client",
            "redis_client",
            "pyjwt",
            "provider_sdks",
            "test_tooling",
        }
        actual_categories = {c.value for c in DependencyCategory}
        missing = required_categories - actual_categories
        assert not missing, f"Missing required dependency categories: {missing}"

    def test_requirements_file_parses_cleanly(self) -> None:
        """Verify requirements.txt exists and parses into non-empty pinned packages."""
        reqs_file = BACKEND_DIR / "requirements.txt"
        assert reqs_file.exists(), f"requirements.txt not found at {reqs_file}"
        parsed = parse_requirements_file(reqs_file)
        assert len(parsed) >= 20, f"Expected at least 20 packages, found {len(parsed)}"

        # Check core packages are present
        assert "fastapi" in parsed
        assert "pydantic" in parsed
        assert "redis" in parsed
        assert "qdrant-client" in parsed
        assert "langchain" in parsed
        assert "langgraph" in parsed
        assert "httpx" in parsed
        assert "pyjwt" in parsed

    def test_known_dependencies_map_to_valid_categories(self) -> None:
        """Verify every entry in KNOWN_DEPENDENCIES maps to a valid DependencyCategory enum."""
        for pkg, meta in KNOWN_DEPENDENCIES.items():
            assert isinstance(meta["category"], DependencyCategory), (
                f"Package {pkg} category {meta['category']} is not a valid DependencyCategory"
            )
            assert (
                isinstance(meta["affected_subsystems"], list)
                and len(meta["affected_subsystems"]) > 0
            )
            assert (
                isinstance(meta["critical_test_paths"], list)
                and len(meta["critical_test_paths"]) > 0
            )

    def test_starlette_transitive_classification(self) -> None:
        """Verify starlette is classified under STARLETTE category and marked as transitive."""
        assert resolve_category("starlette") == DependencyCategory.STARLETTE
        assert KNOWN_DEPENDENCIES["starlette"]["is_direct"] is False
        assert (
            KNOWN_DEPENDENCIES["starlette"]["category"] == DependencyCategory.STARLETTE
        )

    def test_normalize_package_name_variants(self) -> None:
        """Verify package normalization handles underscores, brackets, and version specifiers."""
        assert normalize_package_name("redis[hiredis]==8.1.0") == "redis"
        assert normalize_package_name("qdrant_client") == "qdrant-client"
        assert normalize_package_name("LangChain-Core>=1.6.2") == "langchain-core"
        assert normalize_package_name("pyjwt[crypto]") == "pyjwt"
        assert normalize_package_name("uvicorn[standard]") == "uvicorn"

    def test_manifest_construction_and_installed_versions(self) -> None:
        """Verify build_dependency_manifest populates specifications with real runtime versions."""
        manifest = build_dependency_manifest(BACKEND_DIR)
        assert len(manifest) >= 25

        # Check fastapi specification
        fastapi_spec = manifest.get("fastapi")
        assert fastapi_spec is not None
        assert fastapi_spec.category == DependencyCategory.FASTAPI
        assert fastapi_spec.declared_spec == "0.141.1"
        assert fastapi_spec.installed_version is not None
        assert Version(fastapi_spec.installed_version) >= Version("0.115.0")

        # Check pydantic specification
        pydantic_spec = manifest.get("pydantic")
        assert pydantic_spec is not None
        assert pydantic_spec.category == DependencyCategory.PYDANTIC
        assert pydantic_spec.installed_version is not None

        # Check starlette specification
        starlette_spec = manifest.get("starlette")
        assert starlette_spec is not None
        assert starlette_spec.category == DependencyCategory.STARLETTE
        assert starlette_spec.is_direct is False
        assert starlette_spec.installed_version is not None

    def test_pyproject_minimum_bounds_compatible_with_requirements(self) -> None:
        """Verify pyproject.toml minimum bounds are <= the pinned versions in requirements.txt."""
        reqs = parse_requirements_file(BACKEND_DIR / "requirements.txt")

        # Key minimum bounds declared in pyproject.toml
        pyproject_mins = {
            "fastapi": "0.115.0",
            "uvicorn": "0.32.0",
            "pydantic": "2.10.0",
            "pydantic-settings": "2.6.0",
            "langgraph": "0.2.60",
            "langchain": "0.3.14",
            "langchain-core": "0.3.29",
            "pyjwt": "2.10.0",
            "cryptography": "44.0.0",
            "redis": "5.2.1",
            "qdrant-client": "1.12.1",
            "httpx": "0.28.1",
            "tiktoken": "0.8.0",
        }

        for pkg, min_ver in pyproject_mins.items():
            pinned_ver = reqs.get(pkg)
            assert pinned_ver is not None, f"Package {pkg} missing in requirements.txt"
            assert Version(pinned_ver) >= Version(min_ver), (
                f"Pinned version {pinned_ver} for {pkg} is lower than declared minimum {min_ver}"
            )

    def test_impacted_test_paths_resolution(self) -> None:
        """Verify get_impacted_test_paths returns correct test suites for given packages."""
        paths_fastapi = get_impacted_test_paths(["fastapi"])
        assert "tests/contract/test_api_contract.py" in paths_fastapi
        assert "tests/integration/test_endpoints.py" in paths_fastapi

        paths_redis = get_impacted_test_paths(["redis"])
        assert "tests/integration/test_r_func_03_cache_behavior.py" in paths_redis

        paths_multi = get_impacted_test_paths(["qdrant-client", "langgraph"])
        assert "tests/integration/test_agent_platform.py" in paths_multi
        assert "tests/unit/test_rag_embedding_and_points.py" in paths_multi
