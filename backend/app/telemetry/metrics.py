"""Telemetry and metrics aggregation for production observability.

Provides thread-safe, low-overhead metrics collection for:
- Request latency and counts
- Provider latency, errors, and retries
- Stream active gauges, duration, and client cancellations
- Cache hit/miss accounting
- RAG latency and token optimization
- Token usage and cost metrics

Guarantees:
- Zero high-cardinality label explosion (normalized route paths)
- Zero secret or raw prompt leakage in metric labels and telemetry entries
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

# Normalization regex for dynamic path segments (UUIDs, hexadecimal IDs, digits)
_HEX_UUID_RE = re.compile(
    r"/(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|task-[a-zA-Z0-9_-]+|[0-9]+)(?=/|$)"
)


def normalize_metric_path(path: str) -> str:
    """Normalize dynamic parameters from URL path to prevent metric cardinality explosion."""
    normalized = _HEX_UUID_RE.sub("/:id", path)
    return normalized or "/"


class MetricsSnapshot(BaseModel):
    """Structured snapshot of active platform metrics."""

    timestamp: float = Field(default_factory=time.time)
    uptime_seconds: float = Field(default=0.0)
    http_requests_total: dict[str, int] = Field(default_factory=dict)
    http_request_duration_ms_avg: dict[str, float] = Field(default_factory=dict)
    provider_requests_total: dict[str, int] = Field(default_factory=dict)
    provider_latency_ms_avg: dict[str, float] = Field(default_factory=dict)
    provider_errors_total: dict[str, int] = Field(default_factory=dict)
    active_streams: int = Field(default=0)
    stream_cancellations_total: dict[str, int] = Field(default_factory=dict)
    stream_duration_ms_avg: float = Field(default=0.0)
    cache_operations_total: dict[str, int] = Field(default_factory=dict)
    failover_events_total: dict[str, int] = Field(default_factory=dict)
    tokens_consumed_total: dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd_total: float = Field(default=0.0)
    optimization_decisions_total: int = Field(default=0)
    cost_savings_usd_total: float = Field(default=0.0)
    safety_incidents_total: dict[str, int] = Field(default_factory=dict)
    stream_ttft_ms_avg: dict[str, float] = Field(default_factory=dict)
    agent_tasks_total: dict[str, int] = Field(default_factory=dict)
    agent_runs_total: dict[str, int] = Field(default_factory=dict)
    agent_tool_calls_total: dict[str, int] = Field(default_factory=dict)
    agent_revisions_total: dict[str, int] = Field(default_factory=dict)
    agent_recovery_success_total: dict[str, int] = Field(default_factory=dict)
    agent_approval_wait_ms_avg: dict[str, float] = Field(default_factory=dict)


class MetricsCollector:
    """In-memory thread-safe metrics collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.time()

        # HTTP metrics: (method, normalized_path, status_code) -> count / sum_ms
        self._http_requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._http_durations: dict[tuple[str, str], list[float]] = defaultdict(list)

        # Provider metrics: (provider, model, status) -> count / sum_ms
        self._provider_requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._provider_latencies: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._provider_errors: dict[tuple[str, str], int] = defaultdict(int)

        # Streaming metrics
        self._active_streams: int = 0
        self._stream_durations: list[float] = []
        self._stream_cancellations: dict[str, int] = defaultdict(int)
        self._stream_ttft: dict[tuple[str, str], list[float]] = defaultdict(list)

        # Cache & Failover metrics
        self._cache_operations: dict[tuple[str, str], int] = defaultdict(int)
        self._failover_events: dict[tuple[str, str, str], int] = defaultdict(int)

        # Token & FinOps metrics
        self._tokens_consumed: dict[str, int] = defaultdict(int)
        self._estimated_cost_usd: float = 0.0

        # Safety & Security incidents (OPS-06, OPS-12)
        self._safety_incidents: dict[tuple[str, str, str], int] = defaultdict(int)

        # Multi-tenant Agent Observability (OPS-17)
        self._agent_tasks: dict[tuple[str, str], int] = defaultdict(int)
        self._agent_runs: dict[tuple[str, str], int] = defaultdict(int)
        self._agent_tool_calls: dict[tuple[str, str, str], int] = defaultdict(int)
        self._agent_revisions: dict[str, int] = defaultdict(int)
        self._agent_recovery_success: dict[str, int] = defaultdict(int)
        self._agent_approval_waits: dict[str, list[float]] = defaultdict(list)

        # Optimization decisions (COST-13)
        self._optimization_decisions: list[dict[str, Any]] = []
        self._cost_savings_usd_total: float = 0.0

    def record_http_request(
        self, method: str, path: str, status_code: int, duration_ms: float
    ) -> None:
        """Record an inbound HTTP request and execution duration."""
        norm_path = normalize_metric_path(path)
        with self._lock:
            self._http_requests[(method.upper(), norm_path, status_code)] += 1
            dur_list = self._http_durations[(method.upper(), norm_path)]
            dur_list.append(duration_ms)
            if len(dur_list) > 500:
                del dur_list[:250]

    def record_provider_request(
        self,
        provider: str,
        model: str,
        status: str,
        duration_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Record an upstream provider invocation and token usage."""
        p_clean = str(provider).lower()
        m_clean = str(model).lower()
        with self._lock:
            self._provider_requests[(p_clean, m_clean, status)] += 1
            lat_list = self._provider_latencies[(p_clean, m_clean)]
            lat_list.append(duration_ms)
            if len(lat_list) > 500:
                del lat_list[:250]

            if prompt_tokens > 0:
                self._tokens_consumed[f"{m_clean}:prompt"] += prompt_tokens
            if completion_tokens > 0:
                self._tokens_consumed[f"{m_clean}:completion"] += completion_tokens
            if cost_usd > 0.0:
                self._estimated_cost_usd += cost_usd

    def record_provider_error(self, provider: str, category: str) -> None:
        """Record an upstream provider failure categorized by error taxonomy."""
        with self._lock:
            self._provider_errors[(str(provider).lower(), str(category).lower())] += 1

    def stream_started(self) -> None:
        """Increment active streaming count."""
        with self._lock:
            self._active_streams += 1

    def stream_completed(self, duration_ms: float) -> None:
        """Decrement active streaming count and record stream duration."""
        with self._lock:
            self._active_streams = max(0, self._active_streams - 1)
            self._stream_durations.append(duration_ms)
            if len(self._stream_durations) > 500:
                del self._stream_durations[:250]

    def record_stream_cancellation(
        self, endpoint: str, reason: str = "client_disconnect"
    ) -> None:
        """Record a stream cancellation or client disconnect."""
        norm_endpoint = normalize_metric_path(endpoint)
        with self._lock:
            self._active_streams = max(0, self._active_streams - 1)
            self._stream_cancellations[f"{norm_endpoint}:{reason}"] += 1

    def record_cache_operation(self, tier: str, outcome: str) -> None:
        """Record cache query outcome (e.g. tier='exact'|'semantic', outcome='hit'|'miss')."""
        with self._lock:
            self._cache_operations[(str(tier).lower(), str(outcome).lower())] += 1

    def record_failover(
        self, from_provider: str, to_provider: str, reason: str
    ) -> None:
        """Record provider failover event."""
        with self._lock:
            self._failover_events[
                (
                    str(from_provider).lower(),
                    str(to_provider).lower(),
                    str(reason).lower(),
                )
            ] += 1

    def record_optimization_decision(
        self,
        tenant_id: str,
        workload_class: str,
        selected_provider: str,
        selected_model: str,
        estimated_input_cost: float,
        cost_savings_usd_per_million: float,
        reason: str = "",
    ) -> None:
        """Record an intelligent model routing optimization decision (COST-13)."""
        with self._lock:
            record = {
                "timestamp": time.time(),
                "tenant_id": tenant_id,
                "workload_class": workload_class,
                "selected_provider": selected_provider,
                "selected_model": selected_model,
                "estimated_input_cost": estimated_input_cost,
                "cost_savings_usd_per_million": cost_savings_usd_per_million,
                "reason": reason,
            }
            self._optimization_decisions.append(record)
            if cost_savings_usd_per_million > 0:
                self._cost_savings_usd_total += (
                    cost_savings_usd_per_million / 1_000_000.0
                )
            if len(self._optimization_decisions) > 1000:
                del self._optimization_decisions[:500]

    def get_optimization_decisions(self) -> list[dict[str, Any]]:
        """Return snapshot of recorded optimization decisions."""
        with self._lock:
            return list(self._optimization_decisions)

    def record_security_incident(
        self, incident_type: str, tenant_id: str = "default", layer: str = "guardrails"
    ) -> None:
        """Record a safety or security incident intercepted by guardrails (OPS-06, OPS-12)."""
        t_clean = (str(tenant_id).strip() or "default")[:36]
        with self._lock:
            self._safety_incidents[
                (str(incident_type).lower(), str(layer).lower(), t_clean)
            ] += 1

    def record_stream_ttft(self, provider: str, model: str, ttft_ms: float) -> None:
        """Record time to first token for streaming responses (OPS-06)."""
        with self._lock:
            ttft_list = self._stream_ttft[(str(provider).lower(), str(model).lower())]
            ttft_list.append(ttft_ms)
            if len(ttft_list) > 500:
                del ttft_list[:250]

    def record_agent_task(self, status: str, tenant_id: str = "default") -> None:
        """Record an agent task status transition (OPS-17)."""
        t_clean = (str(tenant_id).strip() or "default")[:36]
        with self._lock:
            self._agent_tasks[(str(status).lower(), t_clean)] += 1

    def record_agent_run(self, status: str, tenant_id: str = "default") -> None:
        """Record an agent execution run status transition (OPS-17)."""
        t_clean = (str(tenant_id).strip() or "default")[:36]
        with self._lock:
            self._agent_runs[(str(status).lower(), t_clean)] += 1

    def record_agent_tool_call(
        self, tool_name: str, status: str, tenant_id: str = "default"
    ) -> None:
        """Record an agent tool execution by outcome and tenant (OPS-17)."""
        t_clean = (str(tenant_id).strip() or "default")[:36]
        with self._lock:
            self._agent_tool_calls[
                (str(tool_name).lower(), str(status).lower(), t_clean)
            ] += 1

    def record_agent_revision(self, tenant_id: str = "default") -> None:
        """Record an agent plan replan/revision event (OPS-17)."""
        t_clean = (str(tenant_id).strip() or "default")[:36]
        with self._lock:
            self._agent_revisions[t_clean] += 1

    def record_agent_recovery(
        self, tenant_id: str = "default", success: bool = True
    ) -> None:
        """Record an agent error recovery loop outcome (OPS-17)."""
        t_clean = (str(tenant_id).strip() or "default")[:36]
        if success:
            with self._lock:
                self._agent_recovery_success[t_clean] += 1

    def record_agent_approval_wait(
        self, duration_ms: float, tenant_id: str = "default"
    ) -> None:
        """Record agent human approval wait duration (OPS-17)."""
        t_clean = (str(tenant_id).strip() or "default")[:36]
        with self._lock:
            dur_list = self._agent_approval_waits[t_clean]
            dur_list.append(duration_ms)
            if len(dur_list) > 500:
                del dur_list[:250]

    def generate_prometheus_metrics(self) -> str:
        """Generate canonical Prometheus text exposition format (OPS-06)."""
        lines: list[str] = []

        with self._lock:
            # Uptime
            uptime = time.time() - self._start_time
            lines.append("# HELP jakeai_uptime_seconds Process uptime in seconds")
            lines.append("# TYPE jakeai_uptime_seconds gauge")
            lines.append(f"jakeai_uptime_seconds {uptime:.2f}")

            # HTTP requests total
            lines.append(
                "# HELP jakeai_http_requests_total Total incoming HTTP requests"
            )
            lines.append("# TYPE jakeai_http_requests_total counter")
            for (m, p, http_status), count in sorted(self._http_requests.items()):
                lines.append(
                    f'jakeai_http_requests_total{{method="{m}",path="{p}",status="{http_status}"}} {count}'
                )

            # HTTP request duration avg
            lines.append(
                "# HELP jakeai_http_request_duration_ms_avg Average HTTP request duration in ms"
            )
            lines.append("# TYPE jakeai_http_request_duration_ms_avg gauge")
            for (m, p), d in sorted(self._http_durations.items()):
                if d:
                    avg_d = sum(d) / len(d)
                    lines.append(
                        f'jakeai_http_request_duration_ms_avg{{method="{m}",path="{p}"}} {avg_d:.2f}'
                    )

            # Provider requests total
            lines.append(
                "# HELP jakeai_provider_requests_total Total upstream LLM provider requests"
            )
            lines.append("# TYPE jakeai_provider_requests_total counter")
            for (p, m, prov_status), count in sorted(self._provider_requests.items()):
                lines.append(
                    f'jakeai_provider_requests_total{{provider="{p}",model="{m}",status="{prov_status}"}} {count}'
                )

            # Provider latency avg
            lines.append(
                "# HELP jakeai_provider_latency_ms_avg Average provider latency in ms"
            )
            lines.append("# TYPE jakeai_provider_latency_ms_avg gauge")
            for (p, m), d in sorted(self._provider_latencies.items()):
                if d:
                    avg_l = sum(d) / len(d)
                    lines.append(
                        f'jakeai_provider_latency_ms_avg{{provider="{p}",model="{m}"}} {avg_l:.2f}'
                    )

            # Provider errors
            lines.append(
                "# HELP jakeai_provider_errors_total Total provider errors by category"
            )
            lines.append("# TYPE jakeai_provider_errors_total counter")
            for (p, c), count in sorted(self._provider_errors.items()):
                lines.append(
                    f'jakeai_provider_errors_total{{provider="{p}",category="{c}"}} {count}'
                )

            # Active streams & cancellations
            lines.append(
                "# HELP jakeai_stream_active Currently active streaming connections"
            )
            lines.append("# TYPE jakeai_stream_active gauge")
            lines.append(f"jakeai_stream_active {self._active_streams}")

            lines.append(
                "# HELP jakeai_stream_cancellations_total Total stream cancellations"
            )
            lines.append("# TYPE jakeai_stream_cancellations_total counter")
            for ep_reason, count in sorted(self._stream_cancellations.items()):
                endpoint, _, reason = ep_reason.partition(":")
                lines.append(
                    f'jakeai_stream_cancellations_total{{endpoint="{endpoint}",reason="{reason}"}} {count}'
                )

            # Stream TTFT avg
            lines.append(
                "# HELP jakeai_stream_ttft_ms_avg Average time to first token in ms"
            )
            lines.append("# TYPE jakeai_stream_ttft_ms_avg gauge")
            for (p, m), ttft_vals in sorted(self._stream_ttft.items()):
                if ttft_vals:
                    avg_ttft = sum(ttft_vals) / len(ttft_vals)
                    lines.append(
                        f'jakeai_stream_ttft_ms_avg{{provider="{p}",model="{m}"}} {avg_ttft:.2f}'
                    )

            # Tokens consumed
            lines.append(
                "# HELP jakeai_tokens_consumed_total Total tokens consumed across models"
            )
            lines.append("# TYPE jakeai_tokens_consumed_total counter")
            for model_type, count in sorted(self._tokens_consumed.items()):
                model, _, token_type = model_type.partition(":")
                lines.append(
                    f'jakeai_tokens_consumed_total{{model="{model}",type="{token_type or "all"}"}} {count}'
                )

            # Cost
            lines.append(
                "# HELP jakeai_estimated_cost_usd_total Estimated cumulative LLM inference cost in USD"
            )
            lines.append("# TYPE jakeai_estimated_cost_usd_total gauge")
            lines.append(
                f"jakeai_estimated_cost_usd_total {self._estimated_cost_usd:.6f}"
            )

            # Safety incidents (OPS-06, OPS-12)
            lines.append(
                "# HELP jakeai_safety_incidents_total Total safety and security incidents intercepted"
            )
            lines.append("# TYPE jakeai_safety_incidents_total counter")
            for (inc_type, layer, t_id), count in sorted(
                self._safety_incidents.items()
            ):
                lines.append(
                    f'jakeai_safety_incidents_total{{incident_type="{inc_type}",layer="{layer}",tenant_id="{t_id}"}} {count}'
                )

            # Agent metrics (OPS-17)
            lines.append(
                "# HELP jakeai_agent_tasks_total Total agent tasks by status and tenant"
            )
            lines.append("# TYPE jakeai_agent_tasks_total counter")
            for (status, t_id), count in sorted(self._agent_tasks.items()):
                lines.append(
                    f'jakeai_agent_tasks_total{{status="{status}",tenant_id="{t_id}"}} {count}'
                )

            lines.append(
                "# HELP jakeai_agent_runs_total Total agent runs by status and tenant"
            )
            lines.append("# TYPE jakeai_agent_runs_total counter")
            for (status, t_id), count in sorted(self._agent_runs.items()):
                lines.append(
                    f'jakeai_agent_runs_total{{status="{status}",tenant_id="{t_id}"}} {count}'
                )

            lines.append(
                "# HELP jakeai_agent_tool_calls_total Total agent tool calls by tool, status, and tenant"
            )
            lines.append("# TYPE jakeai_agent_tool_calls_total counter")
            for (tool, status, t_id), count in sorted(self._agent_tool_calls.items()):
                lines.append(
                    f'jakeai_agent_tool_calls_total{{tool="{tool}",status="{status}",tenant_id="{t_id}"}} {count}'
                )

            lines.append(
                "# HELP jakeai_agent_revisions_total Total agent plan revisions"
            )
            lines.append("# TYPE jakeai_agent_revisions_total counter")
            for t_id, count in sorted(self._agent_revisions.items()):
                lines.append(
                    f'jakeai_agent_revisions_total{{tenant_id="{t_id}"}} {count}'
                )

            lines.append(
                "# HELP jakeai_agent_recovery_success_total Total agent recovery loop successes"
            )
            lines.append("# TYPE jakeai_agent_recovery_success_total counter")
            for t_id, count in sorted(self._agent_recovery_success.items()):
                lines.append(
                    f'jakeai_agent_recovery_success_total{{tenant_id="{t_id}"}} {count}'
                )

        lines.append("")
        return "\n".join(lines)

    def get_snapshot(self) -> MetricsSnapshot:
        """Generate structured snapshot of all captured metrics."""
        now = time.time()
        with self._lock:
            uptime = round(now - self._start_time, 2)

            http_reqs = {
                f"{m} {p} -> {s}": count
                for (m, p, s), count in self._http_requests.items()
            }
            http_dur_avg = {
                f"{m} {p}": round(sum(d) / len(d), 2)
                for (m, p), d in self._http_durations.items()
                if d
            }
            prov_reqs = {
                f"{p}:{m}:{s}": count
                for (p, m, s), count in self._provider_requests.items()
            }
            prov_lat_avg = {
                f"{p}:{m}": round(sum(d) / len(d), 2)
                for (p, m), d in self._provider_latencies.items()
                if d
            }
            prov_errs = {
                f"{p}:{c}": count for (p, c), count in self._provider_errors.items()
            }
            stream_dur_avg = (
                round(sum(self._stream_durations) / len(self._stream_durations), 2)
                if self._stream_durations
                else 0.0
            )
            cache_ops = {
                f"{tier}:{outcome}": count
                for (tier, outcome), count in self._cache_operations.items()
            }
            failovers = {
                f"{src}->{dst}:{reason}": count
                for (src, dst, reason), count in self._failover_events.items()
            }
            safety_inc = {
                f"{inc}:{layer}:{tid}": count
                for (inc, layer, tid), count in self._safety_incidents.items()
            }
            ttft_avg = {
                f"{p}:{m}": round(sum(vals) / len(vals), 2)
                for (p, m), vals in self._stream_ttft.items()
                if vals
            }
            agent_tasks = {
                f"{st}:{tid}": count for (st, tid), count in self._agent_tasks.items()
            }
            agent_runs = {
                f"{st}:{tid}": count for (st, tid), count in self._agent_runs.items()
            }
            agent_tools = {
                f"{tool}:{st}:{tid}": count
                for (tool, st, tid), count in self._agent_tool_calls.items()
            }
            appr_avg = {
                tid: round(sum(vals) / len(vals), 2)
                for tid, vals in self._agent_approval_waits.items()
                if vals
            }

            return MetricsSnapshot(
                timestamp=now,
                uptime_seconds=uptime,
                http_requests_total=http_reqs,
                http_request_duration_ms_avg=http_dur_avg,
                provider_requests_total=prov_reqs,
                provider_latency_ms_avg=prov_lat_avg,
                provider_errors_total=prov_errs,
                active_streams=self._active_streams,
                stream_cancellations_total=dict(self._stream_cancellations),
                stream_duration_ms_avg=stream_dur_avg,
                cache_operations_total=cache_ops,
                failover_events_total=failovers,
                tokens_consumed_total=dict(self._tokens_consumed),
                estimated_cost_usd_total=round(self._estimated_cost_usd, 6),
                optimization_decisions_total=len(self._optimization_decisions),
                cost_savings_usd_total=round(self._cost_savings_usd_total, 6),
                safety_incidents_total=safety_inc,
                stream_ttft_ms_avg=ttft_avg,
                agent_tasks_total=agent_tasks,
                agent_runs_total=agent_runs,
                agent_tool_calls_total=agent_tools,
                agent_revisions_total=dict(self._agent_revisions),
                agent_recovery_success_total=dict(self._agent_recovery_success),
                agent_approval_wait_ms_avg=appr_avg,
            )

    def reset(self) -> None:
        """Reset all metrics (primarily for test isolation)."""
        with self._lock:
            self._start_time = time.time()
            self._http_requests.clear()
            self._http_durations.clear()
            self._provider_requests.clear()
            self._provider_latencies.clear()
            self._provider_errors.clear()
            self._active_streams = 0
            self._stream_durations.clear()
            self._stream_cancellations.clear()
            self._stream_ttft.clear()
            self._cache_operations.clear()
            self._failover_events.clear()
            self._tokens_consumed.clear()
            self._estimated_cost_usd = 0.0
            self._safety_incidents.clear()
            self._agent_tasks.clear()
            self._agent_runs.clear()
            self._agent_tool_calls.clear()
            self._agent_revisions.clear()
            self._agent_recovery_success.clear()
            self._agent_approval_waits.clear()
            self._optimization_decisions.clear()
            self._cost_savings_usd_total = 0.0


_global_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Singleton getter for MetricsCollector."""
    global _global_metrics_collector
    if _global_metrics_collector is None:
        _global_metrics_collector = MetricsCollector()
    return _global_metrics_collector


metrics = get_metrics_collector()
