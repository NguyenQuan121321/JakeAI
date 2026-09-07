"""JakeAI Routing and Failover Subsystem.

Provides explicit policy-driven model routing and bounded retry/failover execution.
"""

from app.routing.failover import (
    FailoverConfig,
    FailoverManager,
    get_failover_manager,
)
from app.routing.router import (
    ModelRouter,
    RoutingDecision,
    RoutingPolicy,
    get_model_router,
)

__all__ = [
    "FailoverConfig",
    "FailoverManager",
    "ModelRouter",
    "RoutingDecision",
    "RoutingPolicy",
    "get_failover_manager",
    "get_model_router",
]
