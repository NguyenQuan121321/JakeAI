"""Golden Dataset Coding Agent Regression & Intelligence Preservation Suite.

Verifies Sections 10, 11, 21, 22, 28, 29:
1. Hard Requirement: Intelligence & Correctness Preservation (Rule 37).
   Optimized path MUST NOT be accepted if correctness or test pass rate regresses.
2. Task A (Bug Fix): Target file containing known bug is preserved in conservative mode;
   fixes produce 100% test pass rate.
3. Task B (Authentication Flow): Auth security checks, token hashing, and error handlers
   are preserved without skeletonization in conservative mode.
4. Task C (Cross-File Refactor): Interfaces, types, dependencies across modules preserved.
5. Task D (Architecture Query): Aggressive skeletonization reduces token footprint
   without losing high-level topology.
6. FinOps Total Cost Effectiveness: LLM token reduction + minimal CPU overhead.
"""

from __future__ import annotations

import time

import pytest

from app.optimizer.bpe_tokenizer import BPETokenizer
from app.optimizer.context_optimizer import ContextOptimizer
from app.optimizer.contracts import OptimizationLevel
from app.optimizer.cross_tier_pipeline import CrossTierPipeline

# --------------------------------------------------------------------------
# Golden Dataset Artifacts
# --------------------------------------------------------------------------

TASK_A_BUGGY_CODE = """
def calculate_cart_discount(items: list[dict], coupon_rate: float) -> float:
    \"\"\"Calculate total discounted price for cart items.\"\"\"
    if not items:
        return 0.0
    total = sum(item["price"] * item.get("quantity", 1) for item in items)
    # Bug: Applying discount as multiplication without subtraction
    return total * coupon_rate  # BUGGY: Should be total * (1.0 - coupon_rate)
"""

TASK_B_AUTH_CODE = """
import hashlib
import hmac

class AuthenticationService:
    \"\"\"Zero-trust authentication validator.\"\"\"

    def __init__(self, secret_key: str) -> None:
        if not secret_key or len(secret_key) < 16:
            raise ValueError("Secret key too weak")
        self._secret = secret_key.encode("utf-8")

    def verify_token(self, token: str, signature: str) -> bool:
        \"\"\"Verify HMAC-SHA256 signature to prevent timing attacks.\"\"\"
        expected_sig = hmac.new(self._secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
        # Security Critical: Constant-time comparison
        return hmac.compare_digest(expected_sig, signature)

    def authorize_role(self, role: str, required_role: str) -> bool:
        \"\"\"Enforce role hierarchy.\"\"\"
        roles_hierarchy = {"admin": 3, "editor": 2, "viewer": 1}
        return roles_hierarchy.get(role, 0) >= roles_hierarchy.get(required_role, 99)
"""

TASK_C_MODELS_CODE = """
from pydantic import BaseModel, Field

class OrderItem(BaseModel):
    sku: str = Field(..., min_length=3)
    unit_price_cents: int = Field(..., gt=0)
    quantity: int = Field(default=1, gt=0)

class OrderRequest(BaseModel):
    order_id: str
    items: list[OrderItem]
    tenant_id: str
"""

TASK_D_ARCHITECTURE_CODE = """
class EnterpriseGateway:
    \"\"\"Routes requests and governs perimeter security.\"\"\"
    def route_request(self, path: str):
        # 50 lines of complex internal routing and regex
        return "routed"

class DatabasePool:
    \"\"\"Manages connection pools.\"\"\"
    def acquire(self):
        # Pool acquisition logic
        return None
"""


@pytest.fixture
def cross_tier_pipeline() -> CrossTierPipeline:
    return CrossTierPipeline(
        context_optimizer=ContextOptimizer(),
        tokenizer=BPETokenizer(),
    )


@pytest.mark.asyncio
async def test_task_a_bug_fix_preserves_implementation(
    cross_tier_pipeline: CrossTierPipeline,
) -> None:
    """Task A (Bug Fix): Conservative mode preserves full code logic so bug can be fixed."""
    query = "Fix the bug in calculate_cart_discount where coupon discount is inverted"

    res = await cross_tier_pipeline.process(
        system_instruction="You are an expert Python engineer.",
        user_query=query,
        dynamic_context=TASK_A_BUGGY_CODE,
        model="claude-3-5-sonnet-20241022",
    )

    # Inferred level must be CONSERVATIVE
    assert res.optimized_context.optimization_level == OptimizationLevel.CONSERVATIVE

    # The code body MUST NOT be skeletonized with Ellipsis (...)
    assert "..." not in res.optimized_context.content
    assert "return total * coupon_rate" in res.optimized_context.content
    assert "calculate_cart_discount" in res.optimized_context.content

    # Simulate fix validation
    fixed_code = res.optimized_context.content.replace(
        "return total * coupon_rate", "return total * (1.0 - coupon_rate)"
    )
    namespace: dict = {}
    exec(fixed_code, namespace)  # nosec B102
    calc_func = namespace["calculate_cart_discount"]

    # Test suite validation
    cart = [{"price": 100.0, "quantity": 2}]  # total = 200
    assert calc_func(cart, 0.10) == 180.0  # 10% off of 200 is 180


@pytest.mark.asyncio
async def test_task_b_authentication_preserves_security_checks(
    cross_tier_pipeline: CrossTierPipeline,
) -> None:
    """Task B (Authentication): Security checks, HMAC comparison, error raises are preserved."""
    query = "Update authentication service to support MFA tokens"

    res = await cross_tier_pipeline.process(
        system_instruction="Follow secure coding guidelines.",
        user_query=query,
        dynamic_context=TASK_B_AUTH_CODE,
        model="gpt-4o",
    )

    assert res.optimized_context.optimization_level == OptimizationLevel.CONSERVATIVE
    content = res.optimized_context.content

    # Verify 100% of critical security constructs remain intact
    assert "hmac.compare_digest" in content, (
        "Security regression: timing attack defense stripped!"
    )
    assert "Secret key too weak" in content, (
        "Security regression: key validation check stripped!"
    )
    assert "roles_hierarchy" in content, "Security regression: role hierarchy stripped!"
    assert "..." not in content


@pytest.mark.asyncio
async def test_task_c_cross_file_refactor_preserves_interfaces(
    cross_tier_pipeline: CrossTierPipeline,
) -> None:
    """Task C (Cross-File Refactor): Preserves models and type contracts across files."""
    query = "Refactor OrderRequest schema to add currency field"

    res = await cross_tier_pipeline.process(
        system_instruction="Coding assistant.",
        user_query=query,
        dynamic_context=TASK_C_MODELS_CODE,
        model="gpt-4o",
    )

    assert res.optimized_context.optimization_level == OptimizationLevel.CONSERVATIVE
    content = res.optimized_context.content
    assert "class OrderItem" in content
    assert "class OrderRequest" in content
    assert "unit_price_cents" in content


@pytest.mark.asyncio
async def test_task_d_architecture_analysis_aggressive_skeletonization(
    cross_tier_pipeline: CrossTierPipeline,
) -> None:
    """Task D (Architecture Query): Aggressive skeletonization safely reduces tokens without losing structure."""
    query = "Where is routing implemented and what is the system architecture overview?"

    res = await cross_tier_pipeline.process(
        system_instruction="Architecture consultant.",
        user_query=query,
        dynamic_context=TASK_D_ARCHITECTURE_CODE,
        model="claude-3-5-sonnet-20241022",
    )

    assert res.optimized_context.optimization_level == OptimizationLevel.AGGRESSIVE
    content = res.optimized_context.content

    # Verify structural topology is preserved
    assert "class EnterpriseGateway" in content
    assert "class DatabasePool" in content
    assert "def route_request" in content
    assert "def acquire" in content

    # Verify implementation bodies were compressed
    assert "..." in content
    assert res.token_metrics.removed_tokens > 0
    assert res.token_metrics.reduction_ratio > 0.10


@pytest.mark.asyncio
async def test_performance_and_finops_benchmark(
    cross_tier_pipeline: CrossTierPipeline,
) -> None:
    """Benchmark execution latency, token reduction, and total FinOps cost effectiveness."""
    t0 = time.perf_counter()
    res = await cross_tier_pipeline.process(
        system_instruction="System prompt for benchmarking.",
        user_query="Explain the routing topology of EnterpriseGateway",
        dynamic_context=TASK_D_ARCHITECTURE_CODE * 5,
        model="claude-3-5-sonnet-20241022",
    )
    duration_ms = (time.perf_counter() - t0) * 1000.0

    # Cross-tier pipeline processing should be fast (sub-50ms locally)
    assert duration_ms < 150.0, f"Pipeline exceeded latency budget: {duration_ms:.2f}ms"
    assert res.token_metrics.raw_tokens > res.token_metrics.optimized_tokens
    assert res.fallback_used is False
