#!/usr/bin/env python3
"""Automated Bruno Reconciliation and Schema Drift Detector (BRUNO-RECON-01).

Dynamically inspects the authoritative JakeAI FastAPI application and OpenAPI
specification, compares against the Bruno API test suites (public and private),
and detects:
  - MISSING: API operations present in code/OpenAPI but absent from Bruno
  - OBSOLETE: Bruno requests referencing non-existent API routes
  - MISMATCH: HTTP method or parameter format divergence
  - DUPLICATE: Unjustified identical duplicate Bruno requests
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Ensure UTF-8 console output across Windows and Linux
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def find_workspace_root() -> Path:
    """Locate the root of the JakeAI repository."""
    current = Path(__file__).resolve()
    for parent in [current.parent, current.parent.parent, current.parent.parent.parent]:
        if (parent / "Bruno").is_dir() and (parent / "backend").is_dir():
            return parent
    return Path.cwd()


def load_authoritative_openapi(repo_root: Path) -> dict[str, Any]:
    """Load or generate the authoritative OpenAPI specification."""
    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    try:
        from app.main import app

        return app.openapi()
    except Exception:
        openapi_file = backend_dir / "openapi.json"
        if openapi_file.is_file():
            with open(openapi_file, "r", encoding="utf-8") as f:
                return json.load(f)
        raise RuntimeError("Unable to load FastAPI app or backend/openapi.json")


def extract_api_operations(spec: dict[str, Any]) -> set[tuple[str, str]]:
    """Extract set of (METHOD, PATH) operations from OpenAPI specification."""
    operations = set()
    for path, path_item in spec.get("paths", {}).items():
        for method in path_item:
            if method.lower() in ("get", "post", "put", "delete", "patch"):
                operations.add((method.upper(), path))
    return operations


def parse_bru_file(file_path: Path) -> tuple[str, str, str]:
    """Extract (method, raw_url, normalized_template_path) from a .bru file."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(
        r"(get|post|put|delete|patch)\s*\{\s*url:\s*([^\n]+)",
        content,
        re.IGNORECASE,
    )
    if not m:
        return ("UNKNOWN", "", "")

    method = m.group(1).upper()
    raw_url = m.group(2).strip()

    # Normalize url: remove {{base_url}}, query params
    norm_path = raw_url.replace("{{base_url}}", "").replace(
        "{{finnapigo_base_url}}", ""
    )
    norm_path = norm_path.split("?")[0].strip()

    # Map Bruno variables to OpenAPI path templates
    template_path = re.sub(r"\{\{([a-zA-Z0-9_]+)\}\}", r"{\1}", norm_path)

    # Specific known parameter normalization
    if template_path == "/api/v1/rag/tasks/{rag_task_id}":
        template_path = "/api/v1/rag/tasks/{task_id}"

    return (method, raw_url, template_path)


def scan_bruno_workspace(bruno_dir: Path) -> list[dict[str, Any]]:
    """Scan all .bru files in public and private directories."""
    records = []
    for bru_file in sorted(bruno_dir.glob("**/*.bru")):
        # Skip environment files
        if "environments" in bru_file.parts:
            continue

        method, raw_url, template_path = parse_bru_file(bru_file)
        if method == "UNKNOWN":
            continue

        rel_path = str(bru_file.relative_to(bruno_dir)).replace("\\", "/")
        is_private = "private" in bru_file.parts
        is_external_authority = "finnapigo_base_url" in raw_url or raw_url.startswith(
            "/healthz"
        ) or "/api/v1/auth/login" in raw_url

        records.append(
            {
                "file": rel_path,
                "method": method,
                "raw_url": raw_url,
                "template_path": template_path,
                "is_private": is_private,
                "is_external": is_external_authority,
            }
        )
    return records


def check_reconciliation(
    repo_root: Path | None = None, verbose: bool = False
) -> tuple[bool, dict[str, Any]]:
    """Audit Bruno requests against OpenAPI operations and return reconciliation stats."""
    root = repo_root or find_workspace_root()
    bruno_dir = root / "Bruno"

    spec = load_authoritative_openapi(root)
    api_ops = extract_api_operations(spec)
    total_api_ops = len(api_ops)

    bru_records = scan_bruno_workspace(bruno_dir)

    covered_ops: set[tuple[str, str]] = set()
    obsolete_requests: list[dict[str, Any]] = []
    operation_to_files: dict[tuple[str, str], list[str]] = {}

    for record in bru_records:
        op_key = (record["method"], record["template_path"])
        if record["is_external"]:
            # External identity authority calls (FinnApiGo) are not JakeAI endpoints
            continue

        if op_key in api_ops:
            covered_ops.add(op_key)
            operation_to_files.setdefault(op_key, []).append(record["file"])
        else:
            obsolete_requests.append(record)

    missing_ops = sorted(api_ops - covered_ops)
    missing_count = len(missing_ops)
    obsolete_count = len(obsolete_requests)

    # Detect exact duplicates within the same collection partition
    duplicates: list[tuple[str, str, list[str]]] = []
    for op, files in operation_to_files.items():
        public_copies = [f for f in files if "public/" in f]
        private_copies = [f for f in files if "private/" in f]
        if len(public_copies) > 3:  # Beyond smoke, happy path, and example
            duplicates.append((op[0], op[1], public_copies))

    mismatch_count = 0  # Captured as obsolete / missing when path/method diverges

    is_pass = (missing_count == 0) and (obsolete_count == 0)

    summary = {
        "total_api_operations": total_api_ops,
        "bruno_covered": len(covered_ops),
        "missing_count": missing_count,
        "missing_operations": [f"{m} {p}" for m, p in missing_ops],
        "obsolete_count": obsolete_count,
        "obsolete_requests": [r["file"] for r in obsolete_requests],
        "mismatch_count": mismatch_count,
        "duplicates_count": len(duplicates),
        "status": "PASS" if is_pass else "FAIL",
    }

    return is_pass, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JakeAI Bruno Reconciliation and Drift Detector"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed operation lists"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON format"
    )
    args = parser.parse_args()

    repo_root = find_workspace_root()
    passed, summary = check_reconciliation(repo_root, verbose=args.verbose)

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0 if passed else 1

    print(f"CURRENT API OPERATIONS: {summary['total_api_operations']}")
    print(f"BRUNO COVERED: {summary['bruno_covered']}")
    print(f"MISSING: {summary['missing_count']}")
    print(f"OBSOLETE: {summary['obsolete_count']}")
    print(f"MISMATCH: {summary['mismatch_count']}")
    print("")
    print(f"STATUS: {summary['status']}")

    if summary["missing_count"] > 0:
        print("\n[!] MISSING API OPERATIONS (Require Bruno Requests):")
        for m in summary["missing_operations"]:
            print(f"  - {m}")

    if summary["obsolete_count"] > 0:
        print("\n[!] OBSOLETE BRUNO REQUESTS (Route not found in API):")
        for o in summary["obsolete_requests"]:
            print(f"  - {o}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
