"""DevOps & Codebase Audit Bot REST API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.context import TenantContext
from app.core.security import get_current_tenant
from app.services.devops_bot import PRAuditResult, get_audit_bot

router = APIRouter()


class PRAuditRequest(BaseModel):
    """Request payload to audit a Pull Request diff."""

    repo: str = Field(..., description="Repository full name, e.g. organization/repo")
    pr_number: int = Field(..., description="Pull request number")
    title: str = Field(..., description="Pull request title")
    raw_diff: str = Field(..., description="Raw git unified diff content")


class ChangelogRequest(BaseModel):
    """Request payload to synthesize release notes from PR titles and commits."""

    pr_titles: list[str] = Field(
        default_factory=list, description="List of merged PR titles"
    )
    commits: list[str] | None = Field(
        default=None, description="List of commit messages"
    )
    webhook_url: str | None = Field(
        default=None, description="Optional Slack/Discord webhook to broadcast to"
    )


class ChangelogResponse(BaseModel):
    """Generated release notes and broadcast status."""

    changelog_markdown: str
    broadcast_sent: bool


@router.post("/audit-pr", response_model=PRAuditResult)
async def audit_pull_request(
    request: PRAuditRequest,
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Analyze a pull request diff with zero-cost pruning, security scan, and test scaffolding."""
    bot = get_audit_bot()
    return bot.audit_pull_request(
        repo=request.repo,
        pr_number=request.pr_number,
        title=request.title,
        raw_diff=request.raw_diff,
        tenant_id=context.tenant_id,
    )


@router.post("/changelog", response_model=ChangelogResponse)
async def generate_changelog(
    request: ChangelogRequest,
    _context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Generate structured markdown release notes and optionally broadcast to Slack/Discord."""
    bot = get_audit_bot()
    changelog = bot.summarize_changelog(
        pr_titles=request.pr_titles,
        commits=request.commits,
    )

    broadcast_sent = False
    if request.webhook_url:
        payload = {"text": changelog, "content": changelog}
        broadcast_sent = await bot.broadcast_to_webhook(request.webhook_url, payload)

    return {
        "changelog_markdown": changelog,
        "broadcast_sent": broadcast_sent,
    }
