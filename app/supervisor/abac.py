"""
Attribute-Based Access Control (ABAC) for tool execution.

Deliberately simple: a role hierarchy (guest < analyst < developer < admin)
plus a per-tool minimum-role map. This is easy to audit at a glance, which
matters more for a project like this than theoretical flexibility — see the
README for why a real deployment would likely move to a policy engine
(OPA/Rego, Cedar) once the ruleset grows past what fits on one screen.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import Role

# Ordered weakest -> strongest. Index = privilege level.
ROLE_HIERARCHY: list[Role] = [Role.GUEST, Role.ANALYST, Role.DEVELOPER, Role.ADMIN]

# Minimum role required to invoke each tool. Names match GitHub's OFFICIAL
# MCP server (github/github-mcp-server) exactly. Tools not listed here
# default to ADMIN-only (fail closed, not fail open).
TOOL_MIN_ROLE: dict[str, Role] = {
    # Read-only / low-risk
    "search_repositories": Role.GUEST,
    "get_issue": Role.GUEST,
    "list_pull_requests": Role.GUEST,
    "get_workflow_run": Role.ANALYST,
    "search_code": Role.ANALYST,
    # Write actions
    "create_issue": Role.DEVELOPER,
    "add_issue_comment": Role.DEVELOPER,
    "create_pull_request": Role.DEVELOPER,
    "create_branch": Role.DEVELOPER,
    # Destructive / high-privilege — ADMIN minimum, and separately forced
    # through HITL regardless of role (see orchestrator.py + HIGH_RISK_TOOLS).
    "merge_pull_request": Role.ADMIN,
    "create_or_update_file": Role.ADMIN,
    "create_release": Role.ADMIN,
    # Generic conversational tools (non-GitHub)
    "get_system_status": Role.GUEST,
    "query_database": Role.ANALYST,
}


@dataclass
class ABACResult:
    allowed: bool
    reason: str


def _privilege_level(role: Role) -> int:
    return ROLE_HIERARCHY.index(role)


def check_permission(role: Role, tool_name: str) -> ABACResult:
    """Return whether `role` may invoke `tool_name`, fail-closed on unknown tools."""
    required_role = TOOL_MIN_ROLE.get(tool_name, Role.ADMIN)

    if _privilege_level(role) >= _privilege_level(required_role):
        return ABACResult(
            allowed=True,
            reason=f"Role '{role.value}' meets minimum required role '{required_role.value}' for '{tool_name}'",
        )

    return ABACResult(
        allowed=False,
        reason=f"Role '{role.value}' is below minimum required role '{required_role.value}' for '{tool_name}'",
    )
