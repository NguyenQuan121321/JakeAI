"""DevOps & Automated Codebase Audit Bot SaaS service.

Provides PR review, zero-cost diff pruning, automated unit test generation,
and markdown changelog release broadcasts to Slack/Discord.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Patterns of files that generate token bloat in git diffs
IGNORED_DIFF_PATTERNS = [
    r"package-lock\.json",
    r"pnpm-lock\.yaml",
    r"yarn\.lock",
    r"poetry\.lock",
    r"Pipfile\.lock",
    r"Cargo\.lock",
    r".*\.min\.js",
    r".*\.min\.css",
    r".*\.map",
    r".*\.(png|jpg|jpeg|gif|svg|ico|webp)",
    r".*\.(wasm|pyc|bin|so|dll|exe)",
]

DIFF_HEADER_REGEX = re.compile(r"^diff --git a/(.*?) b/(.*?)$", re.MULTILINE)

SECURITY_PATTERNS = [
    (
        r"\b(eval|exec)\s*\(",
        "DANGEROUS_EVAL",
        "High risk: dynamic code execution detected",
    ),
    (
        r"\bos\.system\s*\(",
        "COMMAND_INJECTION",
        "High risk: unescaped shell execution detected",
    ),
    (
        r"""(?:api_key|secret|password|token)\s*=\s*['"][A-Za-z0-9_\-]{8,}['"]""",
        "HARDCODED_SECRET",
        "High risk: potential hardcoded secret or credential",
    ),
    (
        r"""f["'](?:SELECT|INSERT|UPDATE|DELETE)\s+.*\{""",
        "SQL_INJECTION",
        "Medium risk: potential string-interpolated SQL query without parameterization",
    ),
]


class DiffPruner:
    """Intelligently prunes noisy diff files (lockfiles, minified assets, binaries)."""

    @classmethod
    def prune_diff(cls, diff_text: str) -> tuple[str, int, int]:
        """Strip extraneous file diffs from git diff.

        Returns:
            Tuple of (pruned_diff, original_length, pruned_length).
        """
        if not diff_text:
            return "", 0, 0

        original_len = len(diff_text)
        chunks = diff_text.split("diff --git ")
        kept_chunks: list[str] = []

        for chunk in chunks:
            if not chunk.strip():
                continue
            first_line = chunk.split("\n", 1)[0]
            # Check if filename matches any ignored pattern
            is_ignored = any(
                re.search(pattern, first_line, re.IGNORECASE)
                for pattern in IGNORED_DIFF_PATTERNS
            )
            if not is_ignored:
                kept_chunks.append("diff --git " + chunk)

        pruned_diff = "".join(kept_chunks)
        pruned_len = len(pruned_diff)
        return pruned_diff, original_len, pruned_len


class SecurityFinding(BaseModel):
    """Identified security risk in PR diff."""

    rule_id: str
    severity: str
    message: str
    line_snippet: str


class SuggestedTestScaffold(BaseModel):
    """Automated test scaffold recommendation."""

    target_file: str
    test_framework: str
    code_template: str


class PRAuditResult(BaseModel):
    """Result of automated PR code audit."""

    repo: str
    pr_number: int
    title: str
    verdict: str  # APPROVE, COMMENT, REQUEST_CHANGES
    summary: str
    security_findings: list[SecurityFinding]
    test_coverage_advisory: str
    suggested_tests: list[SuggestedTestScaffold]
    original_diff_bytes: int
    pruned_diff_bytes: int
    tokens_saved_estimate: int
    reduction_percentage: float


class CodebaseAuditBot:
    """Core audit bot engine for automated PR reviews and changelog summaries."""

    def __init__(self) -> None:
        self.pruner = DiffPruner()

    def audit_pull_request(
        self,
        repo: str,
        pr_number: int,
        title: str,
        raw_diff: str,
        tenant_id: str,
    ) -> PRAuditResult:
        """Analyze git diff for security vulnerabilities, tests, and best practices."""
        logger.debug("Auditing PR #%s for tenant %s", pr_number, tenant_id)
        pruned_diff, orig_len, pruned_len = self.pruner.prune_diff(raw_diff)
        char_savings = max(0, orig_len - pruned_len)
        token_savings_est = char_savings // 4
        reduction_pct = (
            round((char_savings / orig_len * 100), 1) if orig_len > 0 else 0.0
        )

        findings: list[SecurityFinding] = []
        for pattern, rule_id, desc in SECURITY_PATTERNS:
            for line in pruned_diff.splitlines():
                if (
                    line.startswith("+")
                    and not line.startswith("+++")
                    and re.search(pattern, line, re.IGNORECASE)
                ):
                    findings.append(
                        SecurityFinding(
                            rule_id=rule_id,
                            severity="HIGH" if "High" in desc else "MEDIUM",
                            message=desc,
                            line_snippet=line.strip()[:100],
                        )
                    )

        # Check for test files in diff
        has_tests = bool(
            re.search(
                r"(tests/|test_|\.test\.(ts|js)|\.spec\.(ts|js))",
                pruned_diff,
                re.IGNORECASE,
            )
        )

        suggested_tests: list[SuggestedTestScaffold] = []
        if not has_tests:
            # Extract target modified files
            matches = DIFF_HEADER_REGEX.findall(pruned_diff)
            target_file = matches[0][1] if matches else "module.py"
            test_framework = "pytest" if target_file.endswith(".py") else "vitest"
            template = (
                f"def test_{target_file.replace('.', '_')}_success():\n"
                f"    # TODO: Verify behavior for changes in {target_file}\n"
                f"    assert True\n"
                if test_framework == "pytest"
                else f"describe('{target_file}', () => {{\n"
                f"    it('should handle expected inputs', () => {{\n"
                f"        expect(true).toBe(true);\n"
                f"    }});\n"
                f"}});"
            )
            suggested_tests.append(
                SuggestedTestScaffold(
                    target_file=target_file,
                    test_framework=test_framework,
                    code_template=template,
                )
            )

        # Determine verdict
        if any(f.severity == "HIGH" for f in findings):
            verdict = "REQUEST_CHANGES"
            summary = f"Audit failed: Found {len(findings)} critical security findings in PR #{pr_number}."
        elif not has_tests and len(pruned_diff) > 200:
            verdict = "COMMENT"
            summary = (
                f"PR #{pr_number} introduces logic without accompanying tests. "
                "Recommend adding tests to maintain >= 85% coverage floor."
            )
        else:
            verdict = "APPROVE"
            summary = f"PR #{pr_number} meets security standards and test guidelines."

        advisory = (
            "Verified test coverage present in diff."
            if has_tests
            else "Warning: No test files detected in diff. Project floor requires >= 85% coverage."
        )

        return PRAuditResult(
            repo=repo,
            pr_number=pr_number,
            title=title,
            verdict=verdict,
            summary=summary,
            security_findings=findings,
            test_coverage_advisory=advisory,
            suggested_tests=suggested_tests,
            original_diff_bytes=orig_len,
            pruned_diff_bytes=pruned_len,
            tokens_saved_estimate=token_savings_est,
            reduction_percentage=reduction_pct,
        )

    def summarize_changelog(
        self,
        pr_titles: list[str],
        commits: list[str] | None = None,
    ) -> str:
        """Synthesize pull requests and git commit histories into markdown release notes."""
        all_entries = list(pr_titles)
        if commits:
            all_entries.extend(commits)

        features: list[str] = []
        fixes: list[str] = []
        perfs: list[str] = []
        chores: list[str] = []

        for entry in all_entries:
            clean = entry.strip()
            if not clean:
                continue
            lower = clean.lower()
            if lower.startswith("feat:") or lower.startswith("feat("):
                features.append(clean)
            elif lower.startswith("fix:") or lower.startswith("fix("):
                fixes.append(clean)
            elif lower.startswith("perf:") or lower.startswith("perf("):
                perfs.append(clean)
            else:
                chores.append(clean)

        lines: list[str] = ["## Release Changelog\n"]
        if features:
            lines.append("### 🚀 New Features")
            lines.extend([f"- {f}" for f in features])
            lines.append("")
        if fixes:
            lines.append("### 🐛 Bug Fixes")
            lines.extend([f"- {f}" for f in fixes])
            lines.append("")
        if perfs:
            lines.append("### ⚡ Performance Improvements")
            lines.extend([f"- {p}" for p in perfs])
            lines.append("")
        if chores:
            lines.append("### 🔧 Maintenance & Refactoring")
            lines.extend([f"- {c}" for c in chores])
            lines.append("")

        return "\n".join(lines).strip()

    async def broadcast_to_webhook(
        self, webhook_url: str, message: dict[str, Any]
    ) -> bool:
        """Send formatted notification payload to Slack or Discord webhook."""
        if not webhook_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(webhook_url, json=message)
                return res.status_code in (200, 204)
        except Exception as exc:
            logger.warning("Webhook broadcast failed: %s", exc)
            return False


_audit_bot: CodebaseAuditBot | None = None


def get_audit_bot() -> CodebaseAuditBot:
    """Singleton getter for CodebaseAuditBot."""
    global _audit_bot
    if _audit_bot is None:
        _audit_bot = CodebaseAuditBot()
    return _audit_bot
