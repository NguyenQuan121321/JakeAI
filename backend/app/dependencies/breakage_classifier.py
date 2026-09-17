"""Automated breakage classification and root cause analysis engine for JakeAI (TEST-10)."""

from __future__ import annotations

import re
from typing import Any

from app.dependencies.manifest import (
    KNOWN_DEPENDENCIES,
    normalize_package_name,
)
from app.dependencies.models import (
    BreakageClassification,
    DependencyCategory,
    DependencyDiff,
    FailureClass,
)

# Known breaking patterns observed in target ecosystem dependencies
SIGNATURE_PATTERNS: list[dict[str, Any]] = [
    {
        "category": DependencyCategory.FASTAPI,
        "regex": r"(AttributeError:.*'FastAPI' object has no attribute 'on_event'|lifespan context manager|deprecated on_event)",
        "failure_class": FailureClass.DEPRECATION_REMOVAL,
        "breaking_api": "fastapi.FastAPI.on_event('startup'|'shutdown')",
        "root_cause": "FastAPI removed deprecated on_event lifecycle handlers in favor of ASGI lifespan context managers.",
    },
    {
        "category": DependencyCategory.FASTAPI,
        "regex": r"(OpenAPI.*drift|SchemaDriftError|missing.*paths|paths count mismatch)",
        "failure_class": FailureClass.SCHEMA_DRIFT,
        "breaking_api": "fastapi.routing.APIRoute or openapi schema generator",
        "root_cause": "FastAPI internal schema generator modified OpenAPI 3.1 parameter or response formatting, creating contract drift.",
    },
    {
        "category": DependencyCategory.PYDANTIC,
        "regex": r"(pydantic\.errors\.PydanticUserError|root_validator|validator.*mode|cannot add field validator)",
        "failure_class": FailureClass.SIGNATURE_MUTATION,
        "breaking_api": "pydantic.root_validator or pydantic.field_validator",
        "root_cause": "Pydantic validator signature or configuration mutation incompatible with declared schema.",
    },
    {
        "category": DependencyCategory.PYDANTIC,
        "regex": r"(ValidationError|Input should be a valid|Value error,.*)",
        "failure_class": FailureClass.VALIDATION_ERROR,
        "breaking_api": "pydantic.BaseModel.model_validate",
        "root_cause": "Pydantic strict schema parsing rejected payload data due to tightened type coercion rules.",
    },
    {
        "category": DependencyCategory.STARLETTE,
        "regex": r"(StreamingResponse.*media_type|EventSourceResponse.*format|starlette\.responses)",
        "failure_class": FailureClass.HTTP_PROTOCOL_ERROR,
        "breaking_api": "starlette.responses.StreamingResponse",
        "root_cause": "Starlette streaming response protocol or header validation changed ASGI chunk delivery semantics.",
    },
    {
        "category": DependencyCategory.HTTPX,
        "regex": r"(unexpected keyword argument 'transport'|proxies.*deprecated|httpx\.AsyncClient)",
        "failure_class": FailureClass.SIGNATURE_MUTATION,
        "breaking_api": "httpx.AsyncClient.__init__",
        "root_cause": "HTTPX client transport parameter or proxy configuration changed signature in new release.",
    },
    {
        "category": DependencyCategory.LANGGRAPH,
        "regex": r"(StateGraph.*add_node|langgraph\.checkpoint|Interrupt.*contract|resume.*signature)",
        "failure_class": FailureClass.SIGNATURE_MUTATION,
        "breaking_api": "langgraph.graph.StateGraph.compile / checkpoint",
        "root_cause": "LangGraph state transition protocol, checkpoint serialization format, or interrupt contract mutated.",
    },
    {
        "category": DependencyCategory.LANGCHAIN,
        "regex": r"(cannot import name.*from 'langchain|Runnable.*invoke|BaseCallbackHandler)",
        "failure_class": FailureClass.IMPORT_ERROR,
        "breaking_api": "langchain_core.runnables.Runnable",
        "root_cause": "LangChain modular refactor relocated or deprecated runnable classes/callbacks from core package.",
    },
    {
        "category": DependencyCategory.QDRANT_CLIENT,
        "regex": r"(qdrant_client\.models\.PointStruct|search.*payload_selector|grpc.*QdrantClient)",
        "failure_class": FailureClass.SIGNATURE_MUTATION,
        "breaking_api": "qdrant_client.QdrantClient.search / upsert",
        "root_cause": "Qdrant client payload structure, vector search parameter, or collection schema signature drift.",
    },
    {
        "category": DependencyCategory.REDIS_CLIENT,
        "regex": r"(RedisError|ConnectionPool.*kwargs|unexpected keyword argument.*max_connections|redis\.asyncio)",
        "failure_class": FailureClass.SIGNATURE_MUTATION,
        "breaking_api": "redis.asyncio.Redis.from_url",
        "root_cause": "Redis client connection pool kwargs or async connection lifecycle deprecated in upstream driver.",
    },
    {
        "category": DependencyCategory.PYJWT,
        "regex": r"(InvalidAlgorithmError|algorithms.*parameter.*required|jwt\.decode)",
        "failure_class": FailureClass.SIGNATURE_MUTATION,
        "breaking_api": "jwt.decode(..., algorithms=[...])",
        "root_cause": "PyJWT enforced mandatory explicit algorithms list in decode() to prevent algorithm confusion vulnerabilities.",
    },
    {
        "category": DependencyCategory.PROVIDER_SDKS,
        "regex": r"(tiktoken.*get_encoding|Encoding.*encode_ordinary|token.*overflow)",
        "failure_class": FailureClass.ATTRIBUTE_ERROR,
        "breaking_api": "tiktoken.get_encoding / encode",
        "root_cause": "Tiktoken tokenizer bpe rank mapping or encoding cache structure changed.",
    },
]


class BreakageClassifier:
    """Classifies dependency regression test failures and generates empirical reports."""

    def __init__(self) -> None:
        self.signature_patterns = SIGNATURE_PATTERNS

    def classify_failure(
        self,
        dependency_diff: DependencyDiff,
        affected_test: str,
        failure_output: str,
    ) -> BreakageClassification:
        """Analyze a test execution failure and emit a structured BreakageClassification."""
        category = dependency_diff.category
        dep_name = dependency_diff.dependency
        old_ver = dependency_diff.old_version
        new_ver = dependency_diff.new_version

        # 1. Detect Failure Class & Match Known Signatures
        matched_class = FailureClass.UNKNOWN
        breaking_api: str | None = None
        root_cause: str | None = None

        for pattern in self.signature_patterns:
            if pattern["category"] == category and re.search(
                pattern["regex"], failure_output, re.IGNORECASE
            ):
                matched_class = pattern["failure_class"]
                breaking_api = pattern["breaking_api"]
                root_cause = pattern["root_cause"]
                # Refine breaking_api if specific import symbol is cited
                import_match = re.search(
                    r"cannot import name '([^']+)'", failure_output
                )
                if import_match:
                    breaking_api = f"{dep_name}.{import_match.group(1)}"
                break

        # If no signature matched, infer generic error pattern
        if matched_class == FailureClass.UNKNOWN:
            if (
                "ImportError" in failure_output
                or "ModuleNotFoundError" in failure_output
            ):
                matched_class = FailureClass.IMPORT_ERROR
                root_cause = f"Package '{dep_name}' v{new_ver} failed to import or missing required symbol in runtime."
                import_match = re.search(
                    r"cannot import name '([^']+)'", failure_output
                )
                if import_match:
                    breaking_api = f"{dep_name}.{import_match.group(1)}"
            elif "AttributeError" in failure_output:
                matched_class = FailureClass.ATTRIBUTE_ERROR
                attr_match = re.search(
                    r"object has no attribute '([^']+)'", failure_output
                )
                breaking_api = (
                    f"{dep_name}.{attr_match.group(1)}"
                    if attr_match
                    else f"{dep_name} attribute"
                )
                root_cause = f"Attribute or method '{breaking_api}' removed or renamed in v{new_ver}."
            elif "TypeError" in failure_output:
                matched_class = FailureClass.SIGNATURE_MUTATION
                type_match = re.search(
                    r"unexpected keyword argument '([^']+)'", failure_output
                )
                breaking_api = (
                    f"{dep_name} argument '{type_match.group(1)}'"
                    if type_match
                    else f"{dep_name} signature"
                )
                root_cause = f"Method signature changed in v{new_ver}; {breaking_api} is no longer accepted."
            elif "ValidationError" in failure_output:
                matched_class = FailureClass.VALIDATION_ERROR
                root_cause = f"Schema validation failed against {dep_name} models after updating to v{new_ver}."
            elif "AssertionError" in failure_output:
                matched_class = FailureClass.ASSERTION_FAILURE
                root_cause = f"Behavioral assertion failed in {affected_test} due to semantic drift in {dep_name} v{new_ver}."
            else:
                matched_class = FailureClass.UNKNOWN
                root_cause = f"Unexpected failure encountered while running {affected_test} against {dep_name} v{new_ver}."

        # 2. Extract concise failure summary
        lines = [
            line.strip() for line in failure_output.strip().splitlines() if line.strip()
        ]
        failure_summary = (
            lines[-1] if lines else "Non-zero exit or test assertion failure"
        )
        if len(lines) > 1 and ("Error" in lines[-2] or "FAILED" in lines[-2]):
            failure_summary = f"{lines[-2]} | {failure_summary}"
        if len(failure_summary) > 200:
            failure_summary = failure_summary[:197] + "..."

        # 3. Generate Actionable Rollback / Revert Recommendation
        meta = KNOWN_DEPENDENCIES.get(normalize_package_name(dep_name), {})
        affected_subsystems = ", ".join(
            meta.get("affected_subsystems", ["Core Platform"])
        )

        recommendation = (
            f"Rollback {dep_name} from {new_ver} to {old_ver} in requirements.txt. "
            f"Evidence: Upstream release v{new_ver} introduced breaking drift in [{breaking_api or matched_class.value}], "
            f"failing test [{affected_test}]. Subsystems impacted: [{affected_subsystems}]. "
            f"Do not silently re-pin to an arbitrary intermediate version without running full regression validation."
        )

        return BreakageClassification(
            dependency=dep_name,
            old_version=old_ver,
            new_version=new_ver,
            failure=failure_summary,
            affected_test=affected_test,
            root_cause=root_cause or "Unclassified dependency regression",
            breaking_api=breaking_api,
            rollback_recommendation=recommendation,
            failure_class=matched_class,
            evidence=failure_output[:500]
            if len(failure_output) > 500
            else failure_output,
        )
