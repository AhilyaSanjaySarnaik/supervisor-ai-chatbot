"""
Orchestrator — the main pipeline every chat request flows through.

    Sanitizer -> (route to agent) -> ABAC -> HITL (if required) -> Execute

This is the only module that's allowed to call sanitize(), check_permission(),
hitl_queue, and the tool executors together — keeping that composition in one
place means the security ordering can't accidentally be bypassed by a caller
that, say, forgets to check ABAC before executing. main.py never touches
those pieces directly; it only calls `handle_chat_request`.
"""
from __future__ import annotations

from app.agents import database_agent, support_agent
from app.models.schemas import ChatRequest, CheckpointResult, LogEntry, PendingAction
from app.supervisor import mcp_client
from app.supervisor.abac import check_permission
from app.supervisor.hitl import hitl_queue
from app.supervisor.sanitizer import sanitize
from app.tools.system_tools import LOCAL_TOOLS

# GitHub-flavored tools go through the MCP client; everything else executes locally.
# Names match GitHub's OFFICIAL MCP server (github/github-mcp-server) exactly.
GITHUB_TOOLS = {
    "search_repositories", "get_issue", "list_pull_requests", "get_workflow_run", "search_code",
    "create_issue", "add_issue_comment", "create_pull_request", "create_branch",
    "merge_pull_request", "create_or_update_file", "create_release",
}

security_log: list[LogEntry] = []


def _log(user_id, role, checkpoint, result, tool_name=None, detail="") -> LogEntry:
    entry = LogEntry(
        user_id=user_id, role=role, checkpoint=checkpoint, result=result,
        tool_name=tool_name, detail=detail,
    )
    security_log.append(entry)
    return entry


def _execute_tool(tool_name: str, arguments: dict) -> dict:
    if tool_name in LOCAL_TOOLS:
        return LOCAL_TOOLS[tool_name](arguments)
    if tool_name in GITHUB_TOOLS:
        result = mcp_client.call_tool(tool_name, arguments)
        return {"success": result.success, "output": result.output, "mode": result.mode}
    return {"error": f"Unknown tool '{tool_name}'"}


def handle_chat_request(req: ChatRequest) -> tuple[CheckpointResult, str, dict | None]:
    """Runs a single chat request through the full security pipeline.
    Returns (status, human_readable_message, detail_dict)."""

    # --- Checkpoint 1: Sanitizer ---
    scan = sanitize(req.message)
    if not scan.is_safe:
        _log(req.user_id, req.role, "sanitizer", CheckpointResult.BLOCKED, detail=scan.reason)
        return CheckpointResult.BLOCKED, f"Request blocked by sanitizer: {scan.reason}", {
            "matched_patterns": scan.matched_patterns
        }
    _log(req.user_id, req.role, "sanitizer", CheckpointResult.PASSED, detail=scan.reason)

    # --- Route to the right agent to interpret intent ---
    if database_agent.QUERY_TRIGGERS.search(req.message):
        decision = database_agent.parse_intent(req.message)
    else:
        decision = support_agent.parse_intent(req.message)

    if not decision.is_tool_call:
        # Pure conversation — nothing to check permissions on, nothing to execute.
        return CheckpointResult.PASSED, decision.reply, None

    tool_name, arguments = decision.tool_name, decision.arguments

    # --- Checkpoint 2: ABAC ---
    abac_result = check_permission(req.role, tool_name)
    if not abac_result.allowed:
        _log(req.user_id, req.role, "abac", CheckpointResult.BLOCKED, tool_name, abac_result.reason)
        return CheckpointResult.BLOCKED, f"Access denied: {abac_result.reason}", {"tool_name": tool_name}
    _log(req.user_id, req.role, "abac", CheckpointResult.PASSED, tool_name, abac_result.reason)

    # --- Checkpoint 3: HITL ---
    if hitl_queue.requires_approval(tool_name):
        pending: PendingAction = hitl_queue.enqueue(
            user_id=req.user_id, role=req.role, tool_name=tool_name,
            arguments=arguments, reason="High-risk tool requires human approval",
        )
        _log(req.user_id, req.role, "hitl", CheckpointResult.QUEUED, tool_name,
             f"Queued for approval (action_id={pending.id})")
        return CheckpointResult.QUEUED, (
            f"'{tool_name}' is a high-risk action and has been queued for human approval "
            f"(action id: {pending.id})."
        ), {"action_id": pending.id, "tool_name": tool_name, "arguments": arguments}

    # --- Execution (only reached if sanitizer + ABAC passed and HITL wasn't required) ---
    result = _execute_tool(tool_name, arguments)
    _log(req.user_id, req.role, "execution", CheckpointResult.PASSED, tool_name, "Executed directly (no HITL required)")
    return CheckpointResult.PASSED, f"Executed '{tool_name}'.", {"tool_name": tool_name, "result": result}


def execute_approved_action(action: PendingAction) -> dict:
    """Called once a human approves a pending HITL action."""
    result = _execute_tool(action.tool_name, action.arguments)
    _log(action.user_id, action.role, "execution", CheckpointResult.PASSED, action.tool_name,
         f"Executed after HITL approval (action_id={action.id})")
    return result
