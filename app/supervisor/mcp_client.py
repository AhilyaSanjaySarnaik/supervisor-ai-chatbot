"""
Proxy client for talking to the GitHub MCP Server.

Two modes, selected by MCP_MODE:

- "mock" (default): simulates tool responses locally. No token, no network,
  no running MCP server required — this is what makes the whole project
  demoable/gradeable out of the box.
- "live": speaks the REAL Model Context Protocol (JSON-RPC over a proper
  transport) using the official `mcp` Python SDK — this is not a plain REST
  call, because the GitHub MCP server doesn't expose one. Two transports are
  supported via GITHUB_MCP_TRANSPORT:

    - "http" (default): GitHub's hosted server at
      https://api.githubcopilot.com/mcp/, over streamable HTTP, authenticated
      with your PAT as a bearer token. Nothing to run locally.
    - "stdio": launches `github-mcp-server` as a local subprocess (via
      Docker) and speaks MCP over its stdin/stdout — requires Docker Desktop
      running. Closer to how MCP is used inside an IDE like Claude Code.

The orchestrator only ever calls `call_tool(name, arguments)` — it has no
idea which mode or transport is behind it, so switching between them is a
config change (.env), never a code change.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

MCP_MODE = os.getenv("MCP_MODE", "mock")
GITHUB_MCP_TRANSPORT = os.getenv("GITHUB_MCP_TRANSPORT", "http")  # "http" or "stdio"
GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")


@dataclass
class ToolCallResult:
    success: bool
    tool_name: str
    output: Any
    mode: str


# ---------------------------------------------------------------------------
# Mock mode — deterministic, fake-but-plausible responses, no network at all.
# ---------------------------------------------------------------------------

def _mock_call(tool_name: str, arguments: dict) -> ToolCallResult:
    import time

    fake_id = int(time.time()) % 10000
    mock_responses: dict[str, Any] = {
        "search_repositories": {"repos": [{"name": "example/repo", "stars": 128}]},
        "get_issue": {"number": arguments.get("issue_number", 1), "title": "Example issue", "state": "open"},
        "list_pull_requests": {"pull_requests": [{"number": 1, "title": "Example PR"}]},
        "create_issue": {"number": fake_id, "title": arguments.get("title", "untitled"), "url": f"https://github.com/example/repo/issues/{fake_id}"},
        "add_issue_comment": {"ok": True, "comment_id": fake_id},
        "create_pull_request": {"number": fake_id, "title": arguments.get("title", "untitled"), "url": f"https://github.com/example/repo/pull/{fake_id}"},
        "create_branch": {"ref": f"refs/heads/{arguments.get('branch', 'new-branch')}"},
        "merge_pull_request": {"merged": True, "sha": f"mock{fake_id:04d}"},
        "create_or_update_file": {"ok": True, "commit": f"mock{fake_id:04d}"},
        "create_release": {"tag": arguments.get("tag_name", "v0.0.1"), "url": f"https://github.com/example/repo/releases/tag/mock{fake_id}"},
        "get_workflow_run": {"status": "completed", "conclusion": "success"},
        "search_code": {"matches": []},
    }
    return ToolCallResult(
        success=True,
        tool_name=tool_name,
        output=mock_responses.get(tool_name, {"note": f"No mock configured for '{tool_name}', but call was simulated."}),
        mode="mock",
    )


# ---------------------------------------------------------------------------
# Live mode — real MCP protocol via the official SDK.
# ---------------------------------------------------------------------------

def _extract_content(call_result: Any) -> Any:
    """MCP tool results come back as a list of content blocks (text, etc).
    Flatten that into something the rest of the app can log/serialize as JSON."""
    parts = []
    for block in getattr(call_result, "content", []) or []:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else str(block))
    return parts[0] if len(parts) == 1 else parts


async def _live_call_http(tool_name: str, arguments: dict) -> ToolCallResult:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    async with streamablehttp_client(GITHUB_MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return ToolCallResult(
                success=not getattr(result, "isError", False),
                tool_name=tool_name,
                output=_extract_content(result),
                mode="live-http",
            )


async def _live_call_stdio(tool_name: str, arguments: dict) -> ToolCallResult:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN},
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return ToolCallResult(
                success=not getattr(result, "isError", False),
                tool_name=tool_name,
                output=_extract_content(result),
                mode="live-stdio",
            )


def _describe_exception(exc: BaseException) -> str:
    """asyncio.TaskGroup (used internally by the MCP SDK's transports) wraps
    real errors — connection refused, DNS failure, 401 auth — inside a generic
    ExceptionGroup. Unwrap it so the message actually tells you what happened."""
    sub_exceptions = getattr(exc, "exceptions", None)
    if sub_exceptions:
        return "; ".join(_describe_exception(e) for e in sub_exceptions)
    return f"{type(exc).__name__}: {exc}"


def _live_call(tool_name: str, arguments: dict) -> ToolCallResult:
    if not GITHUB_TOKEN:
        return ToolCallResult(
            success=False, tool_name=tool_name,
            output={"error": "MCP_MODE=live but GITHUB_PERSONAL_ACCESS_TOKEN is not set in .env"},
            mode="live",
        )
    try:
        coro = (
            _live_call_stdio(tool_name, arguments)
            if GITHUB_MCP_TRANSPORT == "stdio"
            else _live_call_http(tool_name, arguments)
        )
        # FastAPI's `def` (sync) routes run in a worker thread, so starting a
        # fresh event loop here per-call is safe — it never competes with the
        # main asyncio loop. Fine for a demo; a high-throughput deployment
        # would keep a long-lived session instead of reconnecting every call.
        return asyncio.run(coro)
    except ImportError:
        return ToolCallResult(
            success=False, tool_name=tool_name,
            output={"error": "The 'mcp' package is not installed. Run: pip install mcp"},
            mode="live",
        )
    except Exception as exc:  # noqa: BLE001 - surface transport/auth errors to the caller instead of crashing the request
        return ToolCallResult(success=False, tool_name=tool_name, output={"error": _describe_exception(exc)}, mode="live")


def call_tool(tool_name: str, arguments: dict) -> ToolCallResult:
    """Single entry point the orchestrator uses, regardless of mock/live mode."""
    if MCP_MODE == "live":
        return _live_call(tool_name, arguments)
    return _mock_call(tool_name, arguments)
