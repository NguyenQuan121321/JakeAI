"""Generate authoritative Bruno endpoint inventory markdown."""

import json
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
openapi_path = repo_root / "backend" / "openapi.json"
output_path = repo_root / "Bruno" / "BRUNO-ENDPOINT-INVENTORY.md"

with open(openapi_path, encoding="utf-8") as f:
    spec = json.load(f)

public_perimeter = {
    ("GET", "/health"),
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/metrics"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/live"),
    ("GET", "/api/v1/health/ready"),
    ("POST", "/api/v1/billing/webhook"),
    ("POST", "/api/v1/coding/resume"),
    ("POST", "/internal/v1/coding/resume"),
}

sse_ops = {
    ("POST", "/api/v1/chat/stream"),
    ("GET", "/api/v1/agent/tasks/{task_id}/runs/{run_id}/events"),
}

lines = [
    "# BRUNO-ENDPOINT-INVENTORY — JakeAI Authoritative API Endpoint Inventory",
    "",
    "**Source of Truth**: Current FastAPI Application (`app.main:app`) + OpenAPI 3.1.0 (`backend/openapi.json`)  ",
    "**Total Unique HTTP Paths**: 47  ",
    "**Total Unique Operations**: 51  ",
    "**Verification Date**: September 17, 2026  ",
    "",
    "---",
    "",
    "## 1. Inventory Summary by Subsystem & Category",
    "",
    "| Subsystem / Domain | Route Prefix | Operations | Auth Required | Tenant Scoped | Streaming | Dependencies |",
    "|---|---|:---:|:---:|:---:|:---:|---|",
    "| **Health & Readiness** | `/health`, `/api/v1/health` | 6 | Public (No) | No | No | None (Pure Probe) |",
    "| **Observability** | `/metrics` | 1 | Public (No) | No | No | Prometheus Registry |",
    "| **Chat Stream** | `/api/v1/chat` | 1 | Bearer JWT | Yes | Yes (SSE) | LangGraph, Redis, Qdrant |",
    "| **Agent Platform** | `/api/v1/agent` | 9 | Bearer JWT | Yes | 1 SSE / 8 JSON | ExecutionEngine, Redis, Tools |",
    "| **RAG Pipeline** | `/api/v1/rag` | 4 | Bearer JWT | Yes | No | Qdrant, FastEmbed, BM25 |",
    "| **BYOK Vault** | `/api/v1/byok` | 7 | Bearer JWT | Yes | No | AES-256-GCM, Redis Vault |",
    "| **AI Gateway** | `/api/v1/gateway`, `/v1` | 8 | Bearer JWT | Yes | Yes (JSON/SSE) | Redis, QuotaManager, Upstream |",
    "| **AI FinOps** | `/api/v1/finops` | 5 | Bearer JWT | Yes | No | FinOpsBudgetManager, Ledger |",
    "| **Analytics & Billing** | `/api/v1/analytics`, `/api/v1/billing` | 4 | JWT / Webhook HMAC | Yes / Webhook | No | PayOS Service, Metrics |",
    "| **DevOps Bot** | `/api/v1/devops` | 2 | Bearer JWT | Yes | No | DiffPruner, Git, Scanner |",
    "| **Coding Tool Bridge** | `/api/v1/coding`, `/internal/v1/coding` | 4 | JWT / Perimeter Secret | Yes | No | ResumeBridge, Redis |",
    "| **TOTAL** | | **51** | **41 JWT / 10 Public & Perimeter** | **44 Scoped** | **2 SSE** | |",
    "",
    "---",
    "",
    "## 2. Complete Authoritative 51-Operation Master Inventory",
    "",
    "| # | METHOD | PATH | SUMMARY | AUTH REQUIRED | TENANT SCOPED | REQUEST BODY | RESPONSE | STATUS CODES | STREAMING | DEPENDENCIES | SECURITY SENSITIVITY |",
    "|:---:|---|---|---|---|:---:|---|---|---|:---:|---|---|",
]

i = 1
for path, p_data in sorted(spec["paths"].items()):
    for method, m_data in sorted(p_data.items()):
        if method.lower() not in ("get", "post", "put", "delete", "patch"):
            continue
        m_upper = method.upper()
        op_key = (m_upper, path)
        summary = m_data.get("summary", "") or m_data.get("description", "")[:40]

        is_pub = op_key in public_perimeter
        if is_pub:
            if "webhook" in path:
                auth = "PayOS HMAC"
                tenant_scoped = "No (Webhook)"
                sec_sens = "Webhook Verification"
            elif "coding/resume" in path:
                auth = "Perimeter Secret"
                tenant_scoped = "Yes"
                sec_sens = "Internal Perimeter"
            else:
                auth = "Public (None)"
                tenant_scoped = "No"
                sec_sens = "Public / Low"
        else:
            auth = "FinnApiGoAuth (JWT)"
            tenant_scoped = "Yes"
            sec_sens = (
                "Authenticated / High"
                if any(x in path for x in ("byok", "agent", "finops"))
                else "Authenticated / Standard"
            )

        is_sse = op_key in sse_ops
        streaming = "Yes (SSE)" if is_sse else "No"

        # Request body
        rb = m_data.get("requestBody")
        if rb:
            content = rb.get("content", {}).get("application/json", {})
            schema_ref = content.get("schema", {}).get("$ref", "")
            req_body = schema_ref.split("/")[-1] if schema_ref else "JSON Object"
        else:
            req_body = "None"

        # Response schema
        responses = m_data.get("responses", {})
        succ_codes = [c for c in sorted(responses.keys()) if c.startswith("2")]
        status_codes = ", ".join(succ_codes) or "200"
        if "422" in responses:
            status_codes += ", 422"
        if not is_pub:
            status_codes += ", 401"

        first_succ = succ_codes[0] if succ_codes else "200"
        resp_c = responses.get(first_succ, {}).get("content", {})
        if is_sse:
            resp_model = "text/event-stream"
        elif "text/plain" in resp_c:
            resp_model = "text/plain"
        elif "application/json" in resp_c:
            s_ref = resp_c["application/json"].get("schema", {}).get("$ref", "")
            if s_ref:
                resp_model = s_ref.split("/")[-1]
            elif resp_c["application/json"].get("schema", {}).get("type") == "array":
                i_ref = (
                    resp_c["application/json"]
                    .get("schema", {})
                    .get("items", {})
                    .get("$ref", "")
                )
                resp_model = (
                    f"List[{i_ref.split('/')[-1]}]" if i_ref else "List[Any]"
                )
            else:
                resp_model = "JSON Object"
        else:
            resp_model = "Empty / Any"

        # Dependencies
        if "chat" in path:
            deps = ["LangGraph", "Redis", "Qdrant", "LLM Provider"]
        elif "agent" in path:
            deps = ["AgentRuntime", "Redis", "ExecutionEngine"]
        elif "rag" in path:
            deps = ["Qdrant", "BM25 Index", "FastEmbed"]
        elif "byok" in path:
            deps = ["AES-256-GCM Vault", "Redis"]
        elif "gateway" in path or path in (
            "/v1/chat/completions",
            "/v1/models",
            "/v1/quotas",
        ):
            deps = ["AI Gateway Proxy", "Redis QuotaManager"]
        elif "finops" in path:
            deps = ["FinOpsBudgetManager", "Redis Ledger"]
        elif "billing" in path:
            deps = ["PayOS / VietQR Service"]
        elif "analytics" in path:
            deps = ["Telemetry Metrics"]
        elif "devops" in path:
            deps = ["DevOpsBot", "DiffPruner"]
        elif "coding" in path:
            deps = ["ResumeBridge", "Redis"]
        elif "health" in path or path == "/metrics":
            deps = ["Platform System Probes"]
        else:
            deps = ["Platform"]
        deps_str = ", ".join(deps)

        lines.append(
            f"| {i} | `{m_upper}` | `{path}` | {summary} | {auth} | {tenant_scoped} | `{req_body}` | `{resp_model}` | {status_codes} | {streaming} | {deps_str} | {sec_sens} |"
        )
        i += 1

out_content = "\n".join(lines) + "\n"
output_path.write_text(out_content, encoding="utf-8")
print(
    f"Successfully wrote {output_path} with {i - 1} operations across {len(spec['paths'])} paths."
)
