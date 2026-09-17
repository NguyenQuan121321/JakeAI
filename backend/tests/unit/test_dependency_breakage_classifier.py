"""Unit tests for JakeAI Dependency Breakage Classifier (TEST-10 / DEP-002 / CAT-130)."""

from __future__ import annotations

import pytest

from app.dependencies.breakage_classifier import BreakageClassifier
from app.dependencies.models import DependencyCategory, DependencyDiff, FailureClass


@pytest.mark.unit
class TestDependencyBreakageClassifier:
    """Validate empirical breakage classification and root cause analysis across categories."""

    def setup_method(self) -> None:
        self.classifier = BreakageClassifier()

    def test_fastapi_on_event_deprecation_classification(self) -> None:
        """Verify classification of FastAPI removing on_event lifecycle handler."""
        diff = DependencyDiff(
            dependency="fastapi",
            category=DependencyCategory.FASTAPI,
            old_version="0.141.1",
            new_version="0.142.0",
            diff_type="upgrade",
            is_major_bump=False,
            is_minor_bump=True,
        )
        failure_log = (
            "Traceback (most recent call last):\n"
            "  File 'backend/app/main.py', line 45, in <module>\n"
            "    @app.on_event('startup')\n"
            "AttributeError: 'FastAPI' object has no attribute 'on_event'"
        )

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/integration/test_endpoints.py::test_health_endpoint_contract",
            failure_output=failure_log,
        )

        assert res.dependency == "fastapi"
        assert res.old_version == "0.141.1"
        assert res.new_version == "0.142.0"
        assert res.failure_class == FailureClass.DEPRECATION_REMOVAL
        assert "on_event" in (res.breaking_api or "")
        assert "lifespan" in res.root_cause
        assert "Rollback fastapi from 0.142.0 to 0.141.1" in res.rollback_recommendation
        assert "Do not silently re-pin" in res.rollback_recommendation

        # Check formatted dict matches TEST-10 specification keys
        f_dict = res.to_formatted_dict()
        expected_keys = {
            "dependency",
            "old version",
            "new version",
            "failure",
            "affected test",
            "root cause",
            "breaking API if confirmed",
            "rollback/revert recommendation",
        }
        assert set(f_dict.keys()) == expected_keys

    def test_fastapi_openapi_schema_drift_classification(self) -> None:
        """Verify classification of FastAPI OpenAPI breaking schema drift."""
        diff = DependencyDiff(
            dependency="fastapi",
            category=DependencyCategory.FASTAPI,
            old_version="0.141.1",
            new_version="0.142.0",
            diff_type="upgrade",
        )
        failure_log = "SchemaDriftError: OpenAPI drift detected in 3 endpoints. Missing required paths."

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/contract/test_api_contract.py",
            failure_output=failure_log,
        )
        assert res.failure_class == FailureClass.SCHEMA_DRIFT
        assert "OpenAPI" in res.root_cause
        assert "Rollback" in res.rollback_recommendation

    def test_pydantic_validator_mutation_classification(self) -> None:
        """Verify classification of Pydantic validator signature mutation."""
        diff = DependencyDiff(
            dependency="pydantic",
            category=DependencyCategory.PYDANTIC,
            old_version="2.13.5",
            new_version="2.14.0",
            diff_type="upgrade",
        )
        failure_log = (
            "pydantic.errors.PydanticUserError: Cannot add field validator to undefined attribute "
            "root_validator mode is invalid"
        )

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/contract/test_orchestration_contracts.py",
            failure_output=failure_log,
        )
        assert res.failure_class == FailureClass.SIGNATURE_MUTATION
        assert "pydantic" in res.dependency
        assert "validator" in (res.breaking_api or "").lower()

    def test_pydantic_validation_error_classification(self) -> None:
        """Verify classification of Pydantic strict parsing validation error."""
        diff = DependencyDiff(
            dependency="pydantic",
            category=DependencyCategory.PYDANTIC,
            old_version="2.13.5",
            new_version="3.0.0",
            diff_type="upgrade",
            is_major_bump=True,
        )
        failure_log = "ValidationError: 1 validation error for TaskSpec\ninput_data: Input should be a valid string"

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/unit/test_structured_output.py",
            failure_output=failure_log,
        )
        assert res.failure_class == FailureClass.VALIDATION_ERROR
        assert "schema" in res.root_cause.lower()

    def test_starlette_streaming_response_classification(self) -> None:
        """Verify classification of Starlette SSE streaming response contract mutation."""
        diff = DependencyDiff(
            dependency="starlette",
            category=DependencyCategory.STARLETTE,
            old_version="1.6.0",
            new_version="1.7.0",
            diff_type="upgrade",
        )
        failure_log = "TypeError: StreamingResponse.__init__() got an unexpected keyword argument 'media_type'"

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/integration/test_gateway.py",
            failure_output=failure_log,
        )
        assert res.failure_class in (
            FailureClass.HTTP_PROTOCOL_ERROR,
            FailureClass.SIGNATURE_MUTATION,
        )
        assert "StreamingResponse" in (res.breaking_api or "")

    def test_httpx_transport_signature_mutation(self) -> None:
        """Verify classification of HTTPX client argument signature mutation."""
        diff = DependencyDiff(
            dependency="httpx",
            category=DependencyCategory.HTTPX,
            old_version="0.28.1",
            new_version="0.29.0",
            diff_type="upgrade",
        )
        failure_log = "TypeError: AsyncClient.__init__() got an unexpected keyword argument 'transport'"

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/fixtures/client.py",
            failure_output=failure_log,
        )
        assert res.failure_class == FailureClass.SIGNATURE_MUTATION
        assert "AsyncClient" in (res.breaking_api or "")

    def test_langgraph_interrupt_contract_mutation(self) -> None:
        """Verify classification of LangGraph interrupt/checkpoint contract drift."""
        diff = DependencyDiff(
            dependency="langgraph",
            category=DependencyCategory.LANGGRAPH,
            old_version="1.2.11",
            new_version="1.3.0",
            diff_type="upgrade",
        )
        failure_log = "ValueError: Interrupt contract mutated in StateGraph.compile()"

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/integration/test_resume_bridge.py",
            failure_output=failure_log,
        )
        assert res.failure_class == FailureClass.SIGNATURE_MUTATION
        assert "StateGraph" in (res.breaking_api or "")

    def test_langchain_import_error_classification(self) -> None:
        """Verify classification of LangChain modular import relocation."""
        diff = DependencyDiff(
            dependency="langchain",
            category=DependencyCategory.LANGCHAIN,
            old_version="1.4.0",
            new_version="2.0.0",
            diff_type="upgrade",
            is_major_bump=True,
        )
        failure_log = "ImportError: cannot import name 'ChatGenerationChunk' from 'langchain_core.outputs'"

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/unit/test_rag.py",
            failure_output=failure_log,
        )
        assert res.failure_class == FailureClass.IMPORT_ERROR
        assert "ChatGenerationChunk" in (res.breaking_api or "")

    def test_qdrant_client_payload_structure_mutation(self) -> None:
        """Verify classification of Qdrant client PointStruct payload change."""
        diff = DependencyDiff(
            dependency="qdrant-client",
            category=DependencyCategory.QDRANT_CLIENT,
            old_version="1.19.0",
            new_version="2.0.0",
            diff_type="upgrade",
        )
        failure_log = "AttributeError: qdrant_client.models.PointStruct object has no attribute 'payload_selector'"

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/unit/test_rag_embedding_and_points.py",
            failure_output=failure_log,
        )
        assert res.failure_class in (
            FailureClass.SIGNATURE_MUTATION,
            FailureClass.ATTRIBUTE_ERROR,
        )
        assert "qdrant" in res.dependency

    def test_redis_client_connection_kwargs_deprecation(self) -> None:
        """Verify classification of Redis client connection pool kwargs deprecation."""
        diff = DependencyDiff(
            dependency="redis",
            category=DependencyCategory.REDIS_CLIENT,
            old_version="8.1.0",
            new_version="9.0.0",
            diff_type="upgrade",
        )
        failure_log = "RedisError: unexpected keyword argument 'max_connections' in ConnectionPool"

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/integration/test_r_func_03_cache_behavior.py",
            failure_output=failure_log,
        )
        assert res.failure_class == FailureClass.SIGNATURE_MUTATION
        assert "redis" in (res.breaking_api or "").lower()

    def test_pyjwt_strict_algorithm_enforcement(self) -> None:
        """Verify classification of PyJWT mandatory algorithms list enforcement."""
        diff = DependencyDiff(
            dependency="pyjwt",
            category=DependencyCategory.PYJWT,
            old_version="2.13.0",
            new_version="3.0.0",
            diff_type="upgrade",
        )
        failure_log = (
            "InvalidAlgorithmError: algorithms parameter is required in jwt.decode()"
        )

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/contract/test_internal_mutual_auth.py",
            failure_output=failure_log,
        )
        assert res.failure_class == FailureClass.SIGNATURE_MUTATION
        assert "jwt.decode" in (res.breaking_api or "")

    def test_provider_sdk_tiktoken_classification(self) -> None:
        """Verify classification of tiktoken encoding change."""
        diff = DependencyDiff(
            dependency="tiktoken",
            category=DependencyCategory.PROVIDER_SDKS,
            old_version="0.14.0",
            new_version="0.15.0",
            diff_type="upgrade",
        )
        failure_log = "AttributeError: 'Encoding' object has no attribute 'encode_ordinary' in tiktoken"

        res = self.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="tests/unit/test_rag_context_budget.py",
            failure_output=failure_log,
        )
        assert res.failure_class == FailureClass.ATTRIBUTE_ERROR
        assert "tiktoken" in (res.breaking_api or "")
