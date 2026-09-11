"""Canonical Bounded Recovery Engine for self-healing execution runs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.domain.contracts import (
    PlanStep,
    RecoveryAction,
    RecoveryDecision,
    VerificationResult,
    VerificationVerdict,
)

if TYPE_CHECKING:
    from app.agent.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


class RecoveryLimits(BaseModel):
    """Hard bounded limits preventing runaway execution or infinite recovery loops."""

    MAX_STEP_RETRIES: int = Field(default=3, alias="max_step_retries")
    MAX_REPLANS: int = Field(default=2, alias="max_replans")
    MAX_TOTAL_ITERATIONS: int = Field(default=10, alias="max_total_iterations")
    MAX_EXECUTION_TIME_SECONDS: float = Field(
        default=60.0, alias="max_execution_time_seconds"
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def harmonize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "max_total_recovery_seconds" in data and "max_execution_time_seconds" not in data:
                data["max_execution_time_seconds"] = data["max_total_recovery_seconds"]
            if "max_replan_cycles" in data and "max_replans" not in data:
                data["max_replans"] = data["max_replan_cycles"]
        return data


class BoundedRecoveryEngine:
    """Evaluates execution and verification failures to produce deterministic, bounded recovery decisions."""

    def __init__(
        self,
        limits: RecoveryLimits | None = None,
        agent_registry: AgentRegistry | None = None,
    ) -> None:
        self.limits = limits or RecoveryLimits()
        if agent_registry is None:
            from app.agent.registry.agent_registry import get_agent_registry

            self.agent_registry = get_agent_registry()
        else:
            self.agent_registry = agent_registry

    def evaluate_step_failure(
        self,
        step: PlanStep,
        error_message: str,
        current_step_retries: int,
        elapsed_time_seconds: float,
    ) -> RecoveryDecision:
        """Classify step-level error and produce a bounded recovery decision."""
        # 1. Check time limit
        if elapsed_time_seconds >= self.limits.MAX_EXECUTION_TIME_SECONDS:
            return RecoveryDecision(
                action=RecoveryAction.TERMINATE_FAILED,
                step_id=step.step_id,
                reason=f"Recovery aborted: total execution time ({elapsed_time_seconds:.1f}s) exceeded limit.",
                attempt=current_step_retries,
                max_attempts=self.limits.MAX_STEP_RETRIES,
            )

        # 2. Check retry limit
        if current_step_retries >= self.limits.MAX_STEP_RETRIES:
            # Check if another eligible agent can take over this step
            eligible = self.agent_registry.find_eligible(
                required_capabilities=step.required_capabilities,
                required_tools=step.required_tools,
            )
            other_agents = [
                a.agent_id for a in eligible if a.agent_id != step.assigned_agent
            ]
            if other_agents:
                alt_agent = other_agents[0]
                logger.info(
                    "Step %s retries exhausted for agent %s. Switching to alternative agent: %s",
                    step.step_id,
                    step.assigned_agent,
                    alt_agent,
                )
                return RecoveryDecision(
                    action=RecoveryAction.SWITCH_AGENT,
                    step_id=step.step_id,
                    reason=f"Retries exhausted on {step.assigned_agent}; transferring to alternative agent {alt_agent}.",
                    attempt=current_step_retries,
                    max_attempts=self.limits.MAX_STEP_RETRIES,
                    alternative_agent=alt_agent,
                )

            return RecoveryDecision(
                action=RecoveryAction.TERMINATE_FAILED,
                step_id=step.step_id,
                reason=f"Step '{step.step_id}' exceeded max retries ({self.limits.MAX_STEP_RETRIES}). Error: {error_message}",
                attempt=current_step_retries,
                max_attempts=self.limits.MAX_STEP_RETRIES,
            )

        # 3. Classify error type
        err_lower = error_message.lower()
        if "rate limit" in err_lower or "429" in err_lower or "overloaded" in err_lower:
            # Model or provider congestion -> switch model or retry with backoff
            return RecoveryDecision(
                action=RecoveryAction.SWITCH_MODEL,
                step_id=step.step_id,
                reason="Upstream rate limit or congestion detected; switching to alternative provider/model.",
                attempt=current_step_retries + 1,
                max_attempts=self.limits.MAX_STEP_RETRIES,
            )

        if "timeout" in err_lower or "connection" in err_lower:
            # Transient network glitch -> retry
            return RecoveryDecision(
                action=RecoveryAction.RETRY,
                step_id=step.step_id,
                reason=f"Transient network failure in step '{step.step_id}'. Retrying with backoff.",
                attempt=current_step_retries + 1,
                max_attempts=self.limits.MAX_STEP_RETRIES,
            )

        # 4. Tool or logical failure: retry step
        return RecoveryDecision(
            action=RecoveryAction.RETRY,
            step_id=step.step_id,
            reason=f"Step execution failure: {error_message}. Initiating retry attempt {current_step_retries + 1}.",
            attempt=current_step_retries + 1,
            max_attempts=self.limits.MAX_STEP_RETRIES,
        )

    def evaluate_verification_result(
        self,
        verification: VerificationResult,
        current_replans: int,
        elapsed_time_seconds: float,
    ) -> RecoveryDecision:
        """Translate a verification outcome into an explicit recovery decision."""
        if verification.verdict == VerificationVerdict.PASS:
            return RecoveryDecision(
                action=RecoveryAction.NONE,
                reason="All quality gates verified successfully.",
                attempt=current_replans,
                max_attempts=self.limits.MAX_REPLANS,
            )

        if verification.verdict == VerificationVerdict.REJECTED:
            return RecoveryDecision(
                action=RecoveryAction.TERMINATE_REJECTED,
                reason=f"Hard security rejection: {verification.reason}",
                attempt=current_replans,
                max_attempts=self.limits.MAX_REPLANS,
            )

        # If time exceeded
        if elapsed_time_seconds >= self.limits.MAX_EXECUTION_TIME_SECONDS:
            return RecoveryDecision(
                action=RecoveryAction.TERMINATE_FAILED,
                reason=f"Execution budget exceeded ({elapsed_time_seconds:.1f}s) during verification recovery.",
                attempt=current_replans,
                max_attempts=self.limits.MAX_REPLANS,
            )

        # If replan budget exceeded
        if current_replans >= self.limits.MAX_REPLANS:
            return RecoveryDecision(
                action=RecoveryAction.TERMINATE_FAILED,
                reason=(
                    f"Verification failed and maximum replans ({self.limits.MAX_REPLANS}) "
                    f"exhausted: {verification.reason}"
                ),
                attempt=current_replans,
                max_attempts=self.limits.MAX_REPLANS,
            )

        if verification.verdict == VerificationVerdict.NEEDS_REVISION:
            return RecoveryDecision(
                action=RecoveryAction.REPLAN,
                reason=f"Verifier requested revision: {verification.reason}",
                attempt=current_replans + 1,
                max_attempts=self.limits.MAX_REPLANS,
            )

        return RecoveryDecision(
            action=RecoveryAction.TERMINATE_FAILED,
            reason=f"Terminal verification failure: {verification.reason}",
            attempt=current_replans,
            max_attempts=self.limits.MAX_REPLANS,
        )


_default_recovery_engine: BoundedRecoveryEngine | None = None


def get_recovery_engine() -> BoundedRecoveryEngine:
    """Singleton accessor for BoundedRecoveryEngine."""
    global _default_recovery_engine
    if _default_recovery_engine is None:
        _default_recovery_engine = BoundedRecoveryEngine()
    return _default_recovery_engine
