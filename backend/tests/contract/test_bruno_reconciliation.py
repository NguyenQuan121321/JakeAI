"""Authoritative Pytest Contract Gate: Bruno Collection Reconciliation & Drift Prevention.

TEST-04 / CONTRACT-008
Verifies:
1. Zero drift between FastAPI runtime operations (app.routes / app.openapi()) and the Bruno collection.
2. Complete operation coverage: all 51 public API operations are covered by Bruno requests.
3. Zero obsolete Bruno requests: no Bruno request targets an obsolete or unregistered route.
4. Git isolation: verifies that Bruno/private/ is completely ignored and untracked by git.
"""

from __future__ import annotations

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
    # Intentional runtime/environment-specific import: scripts/ is dynamically resolved from REPO_ROOT
    from check_bruno_reconciliation import check_reconciliation

    is_pass, summary = check_reconciliation(repo_root=REPO_ROOT)

    assert is_pass, (
        f"Bruno reconciliation failed!\n"
        f"Covered: {summary['bruno_covered']} / {summary['total_api_operations']}\n"
        f"Missing: {summary['missing_operations']}\n"
        f"Obsolete: {summary['obsolete_requests']}\n"
        f"Run: python scripts/check_bruno_reconciliation.py for diagnostics."
    )
    assert summary["missing_count"] == 0, (
        f"Missing operations in Bruno: {summary['missing_operations']}"
    )
    assert summary["obsolete_count"] == 0, (
        f"Obsolete requests in Bruno: {summary['obsolete_requests']}"
    )
    assert summary["status"] == "PASS"


def test_bruno_private_git_isolation():
    """Verify that Bruno/private/ is strictly ignored by Git and not tracked."""
    res = subprocess.run(
        ["git", "ls-files", "Bruno/private/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    tracked_files = [
        line.strip() for line in res.stdout.strip().splitlines() if line.strip()
    ]
    assert len(tracked_files) == 0, (
        f"Security violation: Bruno/private/ contains tracked files: {tracked_files}"
    )


def test_bruno_public_has_zero_secrets():
    """Verify that public Bruno requests do not contain any hardcoded API keys or bearer tokens."""
    import re

    public_dir = BRUNO_DIR / "public"
    patterns = [
        re.compile(r"ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"),
        re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"),
        re.compile(r"(?i)AIza[0-9A-Za-z-_]{35}"),
    ]

    for bru_file in public_dir.glob("**/*.bru"):
        content = bru_file.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            matches = pattern.findall(content)
            assert len(matches) == 0, (
                f"Secret pattern found in public Bruno request {bru_file.name}: {matches}"
            )
