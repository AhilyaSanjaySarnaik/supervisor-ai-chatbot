"""
Internal tool implementations that don't go through the GitHub MCP client —
e.g. system diagnostics and the mock database query used by database_agent.

These are executed the same way GitHub tools are: only after the Supervisor
(sanitizer -> ABAC -> HITL) has cleared the call. This module has no idea
whether it was reached via a "safe" or "risky" path — it just executes.
"""
from __future__ import annotations

import platform
import time
from typing import Any

from app.agents.database_agent import run_mock_query

_START_TIME = time.time()


def get_system_status(_arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "healthy",
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "python_version": platform.python_version(),
    }


def query_database(arguments: dict[str, Any]) -> dict[str, Any]:
    rows = run_mock_query(arguments)
    return {"rows": rows, "count": len(rows)}


# Registry of tools that execute locally (as opposed to via the GitHub MCP client).
LOCAL_TOOLS = {
    "get_system_status": get_system_status,
    "query_database": query_database,
}
