"""Unit and integration tests for DevOps & Codebase Audit Bot SaaS."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.context import TenantContext
from app.core.security import exchange_obo_token
from app.main import app
from app.services.devops_bot import CodebaseAuditBot, DiffPruner


@pytest.fixture
def auth_headers() -> dict[str, str]:
    context = TenantContext(
        tenant_id="tenant-devops-test",
        user_id="user-devops-456",
        roles=["developer"],
        scopes=["chat:write"],
        permissions=["devops:audit"],
    )
    token = exchange_obo_token(context)
    return {"Authorization": f"Bearer {token}"}


SAMPLE_DIFF_WITH_LOCKFILE = """diff --git a/package-lock.json b/package-lock.json
index 1234567..89abcdef 100644
--- a/package-lock.json
+++ b/package-lock.json
@@ -1,5 +1,5 @@
 {
-  "version": "1.0.0"
+  "version": "1.0.1"
 }
diff --git a/backend/app/calculator.py b/backend/app/calculator.py
index aaaaaaa..bbbbbbb 100644
--- a/backend/app/calculator.py
+++ b/backend/app/calculator.py
@@ -1,3 +1,6 @@
+def add_numbers(a: int, b: int) -> int:
+    return a + b
+
"""

SAMPLE_VULNERABLE_DIFF = """diff --git a/backend/app/executor.py b/backend/app/executor.py
index aaaaaaa..bbbbbbb 100644
--- a/backend/app/executor.py
+++ b/backend/app/executor.py
@@ -1,3 +1,6 @@
+def run_user_code(user_input: str):
+    eval(user_input)
+
"""


def test_diff_pruner_strips_lockfiles():
    """Verify DiffPruner strips package-lock.json and preserves code diffs."""
    pruned, orig_len, pruned_len = DiffPruner.prune_diff(SAMPLE_DIFF_WITH_LOCKFILE)
    assert "package-lock.json" not in pruned
    assert "backend/app/calculator.py" in pruned
    assert pruned_len < orig_len


def test_audit_bot_approves_or_comments():
    """Verify audit bot analyzes PR and detects missing tests."""
    bot = CodebaseAuditBot()
    result = bot.audit_pull_request(
        repo="org/project",
        pr_number=42,
        title="feat: add calculator addition logic",
        raw_diff=SAMPLE_DIFF_WITH_LOCKFILE,
        tenant_id="tenant-1",
    )

    assert result.pr_number == 42
    assert result.verdict in ("COMMENT", "APPROVE")
    assert result.original_diff_bytes > result.pruned_diff_bytes
    assert len(result.suggested_tests) > 0


def test_audit_bot_flags_security_risks():
    """Verify audit bot detects eval execution and requests changes."""
    bot = CodebaseAuditBot()
    result = bot.audit_pull_request(
        repo="org/project",
        pr_number=99,
        title="feat: add executor",
        raw_diff=SAMPLE_VULNERABLE_DIFF,
        tenant_id="tenant-1",
    )

    assert result.verdict == "REQUEST_CHANGES"
    assert len(result.security_findings) > 0
    assert any(f.rule_id == "DANGEROUS_EVAL" for f in result.security_findings)


def test_changelog_synthesis():
    """Verify changelog synthesizes commits and PRs into grouped markdown sections."""
    bot = CodebaseAuditBot()
    prs = [
        "feat(auth): add OAuth2 provider support",
        "fix(gateway): resolve 429 rate limit leak",
        "perf(cache): optimize redis ping verification",
        "chore(deps): bump dependencies",
    ]
    markdown = bot.summarize_changelog(prs)

    assert "## Release Changelog" in markdown
    assert "### 🚀 New Features" in markdown
    assert "### 🐛 Bug Fixes" in markdown
    assert "### ⚡ Performance Improvements" in markdown
    assert "OAuth2 provider" in markdown
    assert "resolve 429" in markdown


@pytest.mark.asyncio
async def test_devops_api_endpoints(auth_headers: dict[str, str]):
    """Verify DevOps REST endpoints: audit-pr and changelog."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Audit PR
        res = await client.post(
            "/api/v1/devops/audit-pr",
            json={
                "repo": "enterprise/jakeai",
                "pr_number": 101,
                "title": "feat: add calculator function",
                "raw_diff": SAMPLE_DIFF_WITH_LOCKFILE,
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["repo"] == "enterprise/jakeai"
        assert data["pr_number"] == 101
        assert "verdict" in data

        # Changelog
        res_change = await client.post(
            "/api/v1/devops/changelog",
            json={
                "pr_titles": [
                    "feat: implement BYOK security",
                    "fix: resolve SSE heartbeat timeout",
                ]
            },
            headers=auth_headers,
        )
        assert res_change.status_code == 200
        change_data = res_change.json()
        assert "Release Changelog" in change_data["changelog_markdown"]
        assert change_data["broadcast_sent"] is False
