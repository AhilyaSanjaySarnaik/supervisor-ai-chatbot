"""
Database Agent — handles data-query intents, routed to the `query_database`
tool. Kept deliberately separate from the support/GitHub agent so the two
domains (internal data vs. external GitHub actions) have independent, easily
auditable intent-matching logic rather than one monolithic parser.

The "database" itself is an in-memory mock table — this agent exists to
demonstrate the *pattern* (agent -> supervisor -> tool), not to be a real
data layer. Swap `MOCK_TABLE` / `_run_mock_query` for a real DB connector
behind the same `query_database` tool contract and nothing else changes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

MOCK_TABLE = [
    {"id": 1, "username": "alice", "role": "admin", "last_login": "2026-09-18"},
    {"id": 2, "username": "bob", "role": "developer", "last_login": "2026-09-19"},
    {"id": 3, "username": "carol", "role": "analyst", "last_login": "2026-09-15"},
    {"id": 4, "username": "dave", "role": "guest", "last_login": "2026-08-30"},
]

QUERY_TRIGGERS = re.compile(r"\b(query|search|look up|find)\b.*\b(user|database|record|table)s?\b", re.I)


@dataclass
class AgentDecision:
    is_tool_call: bool
    tool_name: Optional[str] = None
    arguments: dict[str, Any] = field(default_factory=dict)
    reply: str = ""


def parse_intent(message: str) -> AgentDecision:
    if QUERY_TRIGGERS.search(message):
        username_match = re.search(r"\buser(?:name)?\s+['\"]?(\w+)['\"]?", message, re.I)
        arguments: dict[str, Any] = {}
        if username_match:
            arguments["username"] = username_match.group(1)
        return AgentDecision(is_tool_call=True, tool_name="query_database", arguments=arguments)

    return AgentDecision(
        is_tool_call=False,
        reply="I can query the internal user database — try 'find user bob' or 'query all users'.",
    )


def run_mock_query(arguments: dict) -> list[dict]:
    """Executes the (mock) query. Called by system_tools.query_database after
    the Supervisor has already cleared the request — this function itself
    trusts its input, because trust decisions happen upstream, not here."""
    username = arguments.get("username")
    if username:
        return [row for row in MOCK_TABLE if row["username"].lower() == username.lower()]
    return MOCK_TABLE
