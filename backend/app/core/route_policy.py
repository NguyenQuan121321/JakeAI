"""Complete HTTP policy inventory, including root aliases and in-flight delivery."""

import asyncio
import hmac
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from starlette.routing import compile_path

from app.core.config import get_settings
from app.core.context import set_current_tenant_context
from app.core.identity_state import current_authority
from app.core.security import get_current_tenant


class DeliveryStopped(Exception):
    """Keep a post-start authority failure outside framework HTTP error rendering."""

    def __init__(self, error: HTTPException):
        self.error = error


# Keys are registered route templates, never client-selected permission strings.
USER_POLICY: dict[tuple[str, str], tuple[str, ...]] = {
    ("POST", "/chat/stream"): ("chat:write", "rag:read"),
    ("POST", "/rag/ingest"): ("rag:write",),
    ("GET", "/rag/tasks/{task_id}"): ("rag:read",),
    ("POST", "/rag/query"): ("rag:read",),
    ("POST", "/rag/generate"): ("rag:read", "chat:write"),
    ("POST", "/devops/audit-pr"): ("agent:execute",),
    ("POST", "/devops/changelog"): ("agent:execute",),
    ("POST", "/gateway/chat/completions"): ("chat:write",),
    ("GET", "/gateway/models"): ("chat:read",),
    ("GET", "/gateway/quotas"): ("finops:read",),
    ("POST", "/gateway/quotas"): ("finops:write",),
    ("GET", "/billing/subscription"): ("finops:read",),
    ("GET", "/analytics/dashboard"): ("ops:read",),
    ("GET", "/analytics/metrics"): ("ops:read",),
    ("GET", "/finops/summary"): ("finops:read",),
    ("GET", "/finops/transactions"): ("finops:read",),
    ("GET", "/finops/budget"): ("finops:read",),
    ("POST", "/finops/budget"): ("finops:write",),
    ("GET", "/finops/reconciliation"): ("finops:read",),
    ("POST", "/coding/tool-result"): ("agent:execute",),
    ("POST", "/coding/resume"): ("agent:execute",),
    ("POST", "/agent/tasks"): ("agent:write",),
    ("GET", "/agent/tasks/{task_id}"): ("agent:read",),
    ("POST", "/agent/tasks/{task_id}/runs"): ("agent:execute",),
    ("GET", "/agent/tasks/{task_id}/runs/{run_id}"): ("agent:read",),
    ("GET", "/agent/tasks/{task_id}/runs/{run_id}/events"): ("agent:read",),
    ("POST", "/agent/tasks/{task_id}/runs/{run_id}/cancel"): ("agent:write",),
    ("POST", "/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}"): (
        "agent:approve",
    ),
    ("GET", "/agent/approvals/pending"): ("agent:approve",),
    ("GET", "/agent/metrics"): ("ops:read",),
}
for method, suffix in [
    ("POST", "/keys"),
    ("GET", "/keys"),
    ("POST", "/keys/validate"),
    ("POST", "/keys/{provider}/validate"),
    ("POST", "/keys/{provider}/rotate"),
    ("POST", "/keys/{provider}/revoke"),
    ("DELETE", "/keys/{provider}"),
]:
    USER_POLICY[(method, "/byok" + suffix)] = (
        "byok:read" if method == "GET" else "byok:write",
    )


def policy_for(method: str, path: str) -> tuple[str, ...] | str | None:
    prefix = get_settings().API_V1_STR
    suffix = path[len(prefix) :] if path.startswith(prefix + "/") else path
    if suffix in {
        "/health",
        "/health/live",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
    }:
        return "public"
    if suffix in {"/health/ready", "/metrics"}:
        return "operator"
    if suffix == "/billing/webhook":
        return "payment-signature"
    if suffix.startswith("/v1/"):
        suffix = "/gateway" + suffix[3:]
    if suffix.startswith("/internal/v1/coding/"):
        suffix = "/coding/" + suffix.rsplit("/", 1)[-1]
    return USER_POLICY.get((method, suffix))


class AuthorizationMiddleware:
    """Authorize before route validation, recheck during work and before response bytes."""

    def __init__(self, app: Any):
        self.app = app
        self._schema: Any = None
        self._patterns: list[Any] = []

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            # No WebSocket user protocol is authorized or registered in this application.
            await send({"type": "websocket.close", "code": 1008})
            return
        request = Request(scope, receive)
        if (
            scope["method"] == "OPTIONS"
            and "origin" in request.headers
            and "access-control-request-method" in request.headers
        ):
            # CORS emits only its origin/method/header negotiation response.
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        if path in {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}:
            await self.app(scope, receive, send)
            return
        route_path = None
        params = {}
        schema = request.app.openapi()
        if self._schema is not schema:
            self._patterns = [
                (candidate, compile_path(candidate)[0], operations)
                for candidate, operations in schema["paths"].items()
            ]
            self._schema = schema
        for candidate, regex, operations in self._patterns:
            match = regex.fullmatch(path)
            if match and scope["method"].lower() in operations:
                route_path, params = candidate, match.groupdict()
                break
        if route_path is None:
            await JSONResponse({"detail": "Not found"}, status_code=404)(
                scope, receive, send
            )
            return
        rule = policy_for(scope["method"], route_path)
        binding = current_authority.set(None)
        tenant_binding = set_current_tenant_context(None)
        task = None
        started = False
        try:
            if rule is None:
                raise HTTPException(503, "Route authorization policy unavailable")
            if rule in ("public", "payment-signature"):
                await self.app(scope, receive, send)
                return
            if rule == "operator":
                expected = get_settings().OPERATOR_METRICS_SECRET
                supplied = request.headers.get("x-operator-secret", "")
                if not expected or not hmac.compare_digest(supplied, expected):
                    raise HTTPException(404, "Not found")
                await self.app(scope, receive, send)
                return
            if not isinstance(rule, tuple):
                raise HTTPException(503, "Invalid route authorization policy")
            auth = request.headers.getlist("authorization")
            if len(auth) != 1 or not auth[0].startswith("Bearer "):
                raise HTTPException(
                    401,
                    "Access credential required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            context = await get_current_tenant(
                request,
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth[0][7:]),
            )
            if not context.has_all_permissions(list(rule)):
                raise HTTPException(403, "Insufficient permissions")
            request.state.authority_lease.operation_permissions = rule
            if "finops:write" in rule and "tenant_admin" not in context.roles:
                raise HTTPException(
                    403, "Delegated tenant budget administrator required"
                )
            if route_path.startswith(get_settings().API_V1_STR + "/agent/tasks/"):
                from app.agent.runtime.manager import get_agent_manager

                manager = get_agent_manager()
                try:
                    owned = manager.get_task(params["task_id"], context.tenant_id)
                    if owned.user_id != context.user_id:
                        raise KeyError
                    if "run_id" in params:
                        run = await manager.get_or_restore_run(
                            params["run_id"], context.tenant_id
                        )
                        if (
                            run.run_id != params["run_id"]
                            or run.tenant_id != context.tenant_id
                            or run.task_id != owned.task_id
                            or run.user_id != context.user_id
                        ):
                            raise KeyError
                except (KeyError, PermissionError):
                    raise HTTPException(404, "Not found") from None
            # These surfaces cannot safely convert RAM decisions/checkpoints or
            # caller-supplied identity into durable execution authority (J07).
            if "/coding/" in route_path or "/approvals/" in route_path:
                raise HTTPException(
                    503, "Durable execution authorization is unavailable"
                )
            if route_path.endswith(("/analytics/metrics", "/agent/metrics")):
                raise HTTPException(
                    503, "Process telemetry requires the private operator endpoint"
                )
            lease = request.state.authority_lease

            async def guarded_send(message: Any) -> None:
                nonlocal started
                if message["type"] in {"http.response.start", "http.response.body"}:
                    try:
                        await lease.check()
                    except HTTPException as exc:
                        raise DeliveryStopped(exc) from None
                if message["type"] == "http.response.start":
                    started = True
                await send(message)

            task = asyncio.create_task(self.app(scope, receive, guarded_send))
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10)
                if not done:
                    await lease.check(force=True)
            await task
        except (HTTPException, DeliveryStopped) as failure:
            exc = failure.error if isinstance(failure, DeliveryStopped) else failure
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if started:
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )
            else:
                await JSONResponse(
                    {"detail": exc.detail},
                    status_code=exc.status_code,
                    headers={"Cache-Control": "no-store", **(exc.headers or {})},
                )(scope, receive, send)
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            current_authority.reset(binding)
            tenant_binding.var.reset(tenant_binding)
