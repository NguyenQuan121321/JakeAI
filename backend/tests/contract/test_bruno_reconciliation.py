"""Authoritative Pytest Contract Gate: Bruno Collection Reconciliation & Drift Prevention.

TEST-04 / CONTRACT-008 (Updated under TEST-14)
Verifies:
1. Master Zero Drift: All public client-facing operations are covered in Bruno/public/,
   internal service endpoints are governed by Bruno/private/ & Pytest, and zero obsolete routes exist.
2. Public Endpoint Missing Failure: Reconciliation fails if any public route lacks Bruno/public/ coverage.
3. Internal Endpoint Missing Failure: Reconciliation fails if internal service routes are unaccounted for.
4. Deliberate Pytest-Only Exemption: Registered PYTEST_ONLY endpoints pass with explicit inventory documentation.
5. Obsolete Request Detection: Reconciliation fails if a Bruno file targets a nonexistent API route.
6. Wrong Method Detection: Method mismatches fail the reconciliation check.
7. Wrong Normalized Path Detection: Path template divergence fails the reconciliation check.
8. Public Bruno Zero Secrets: No internal perimeter secrets, production tokens, or API keys in Bruno/public/.
9. Git Isolation: Bruno/private/ is strictly ignored by Git and 0 files are tracked.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
BRUNO_DIR = REPO_ROOT / "Bruno"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def test_bruno_collection_zero_drift():
    """Verify that Bruno collection has 100% operation coverage with 0 missing and 0 obsolete requests."""
    from check_bruno_reconciliation import check_reconciliation

    is_pass, summary = check_reconciliation(repo_root=REPO_ROOT)

    assert is_pass, (
        f"Bruno reconciliation failed!\n"
        f"Public Covered: {summary['public_covered_count']} / {summary['public_operations_count']}\n"
        f"Missing Public: {summary['missing_public_operations']}\n"
        f"Internal Covered: {summary['internal_covered_count']} / {summary['internal_operations_count']}\n"
        f"Missing Internal: {summary['missing_internal_operations']}\n"
        f"Obsolete: {summary['obsolete_requests']}\n"
        f"Run: python scripts/check_bruno_reconciliation.py for diagnostics."
    )
    assert summary["missing_public_count"] == 0, (
        f"Missing public operations in Bruno: {summary['missing_public_operations']}"
    )
    assert summary["missing_internal_count"] == 0, (
        f"Missing internal operations in Bruno: {summary['missing_internal_operations']}"
    )
    assert summary["obsolete_count"] == 0, (
        f"Obsolete requests in Bruno: {summary['obsolete_requests']}"
    )
    assert summary["status"] == "PASS"


def test_public_endpoint_missing_fails():
    """Verify that a public API operation missing from Bruno/public triggers a FAIL verdict."""
    from check_bruno_reconciliation import check_reconciliation

    # Simulate removing a public endpoint from covered operations
    is_pass_baseline, summary_baseline = check_reconciliation(repo_root=REPO_ROOT)
    assert is_pass_baseline, "Baseline must pass before simulating public omission"

    # Simulate dropping one public endpoint from public coverage
    synthetic_covered = {
        (op.split(" ", 1)[0], op.split(" ", 1)[1])
        for op in summary_baseline.get("public_covered_ops", [])
    }
    # Drop one public operation
    target_op = ("GET", "/health")
    synthetic_covered.discard(target_op)

    is_pass, summary = check_reconciliation(
        repo_root=REPO_ROOT,
        override_public_covered=synthetic_covered,
    )
    assert not is_pass, "Omitting a public endpoint must trigger FAIL verdict"
    assert summary["missing_public_count"] > 0
    assert "GET /health" in summary["missing_public_operations"]


def test_internal_endpoint_missing_fails():
    """Verify that an internal service endpoint missing from private Bruno triggers a FAIL verdict."""
    from check_bruno_reconciliation import check_reconciliation

    # Simulate dropping internal endpoint coverage in private suite
    empty_private_coverage: set[tuple[str, str]] = set()

    is_pass, summary = check_reconciliation(
        repo_root=REPO_ROOT,
        override_private_covered=empty_private_coverage,
    )
    assert not is_pass, "Omitting an internal endpoint must trigger FAIL verdict"
    assert summary["missing_internal_count"] > 0
    assert any("coding" in op for op in summary["missing_internal_operations"])


def test_deliberately_pytest_only_endpoint_passes():
    """Verify that an operation explicitly registered as PYTEST_ONLY passes without public Bruno request."""
    from check_bruno_reconciliation import check_reconciliation, classify_operation

    # Designate an endpoint as PYTEST_ONLY
    custom_registry = {("POST", "/api/v1/billing/webhook")}

    # With the endpoint registered as PYTEST_ONLY, verify classification
    classification = classify_operation(
        "POST",
        "/api/v1/billing/webhook",
        pytest_registry=custom_registry,
    )
    assert classification["exposure"] == "PYTEST_ONLY"
    assert classification["bruno_required"] is False
    assert classification["test_layer"] == "pytest"

    # Verify check_reconciliation correctly accounts for it in summary
    is_pass, summary = check_reconciliation(
        repo_root=REPO_ROOT,
        pytest_registry=custom_registry,
    )
    assert is_pass
    assert "POST /api/v1/billing/webhook" in summary["pytest_only_operations"]


def test_obsolete_bruno_request_fails():
    """Verify that a Bruno request referencing a non-existent API route triggers a FAIL verdict."""
    from check_bruno_reconciliation import check_reconciliation

    synthetic_obsolete = [
        {"file": "public/02 — Chat/99 — Nonexistent Obsolete Route.bru"}
    ]

    is_pass, summary = check_reconciliation(
        repo_root=REPO_ROOT,
        override_obsolete=synthetic_obsolete,
    )
    assert not is_pass, "Obsolete Bruno requests must trigger FAIL verdict"
    assert summary["obsolete_count"] == 1


def test_wrong_method_fails():
    """Verify that an incorrect HTTP method causes the expected operation to remain missing."""
    from check_bruno_reconciliation import check_reconciliation

    # Substitute POST /api/v1/chat/stream with GET /api/v1/chat/stream
    synthetic_covered = {("GET", "/api/v1/chat/stream")}

    is_pass, summary = check_reconciliation(
        repo_root=REPO_ROOT,
        override_public_covered=synthetic_covered,
    )
    assert not is_pass, "Wrong HTTP method must result in missing operation"
    assert "POST /api/v1/chat/stream" in summary["missing_public_operations"]


def test_wrong_normalized_path_fails():
    """Verify that an unnormalized path template causes the expected operation to remain missing."""
    from check_bruno_reconciliation import check_reconciliation

    # Send hardcoded path instead of template {task_id}
    synthetic_covered = {("GET", "/api/v1/agent/tasks/task-12345")}

    is_pass, summary = check_reconciliation(
        repo_root=REPO_ROOT,
        override_public_covered=synthetic_covered,
    )
    assert not is_pass, "Unnormalized path parameter must result in missing operation"
    assert "GET /api/v1/agent/tasks/{task_id}" in summary["missing_public_operations"]


def test_public_bruno_has_zero_secrets_and_no_internal_secrets():
    """Verify that public Bruno requests contain zero production credentials or internal gateway secrets."""
    public_dir = BRUNO_DIR / "public"
    patterns = [
        re.compile(r"ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"),
        re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"),
        re.compile(r"(?i)AIza[0-9A-Za-z-_]{35}"),
        re.compile(r"jakeai-finnapigo-shared-internal-secret-32b"),
    ]

    for bru_file in public_dir.glob("**/*.bru"):
        content = bru_file.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            matches = pattern.findall(content)
            assert len(matches) == 0, (
                f"Secret pattern violation found in public Bruno request {bru_file.name}: {matches}"
            )


def test_bruno_private_git_isolation():
    """Verify that Bruno/private/ is strictly ignored by Git and not tracked."""
    res_ls = subprocess.run(
        ["git", "ls-files", "Bruno/private/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    tracked_files = [
        line.strip() for line in res_ls.stdout.strip().splitlines() if line.strip()
    ]
    assert len(tracked_files) == 0, (
        f"Security violation: Bruno/private/ contains tracked files: {tracked_files}"
    )

    res_ignore = subprocess.run(
        ["git", "check-ignore", "-v", "Bruno/private/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_ignore.returncode == 0, (
        f"Git ignore violation: Bruno/private/ is not properly ignored by .gitignore: {res_ignore.stderr}"
    )
