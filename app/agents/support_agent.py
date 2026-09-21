"""
Support Agent — handles general conversation and GitHub-oriented intents.

Tool names here match GitHub's OFFICIAL MCP server (github/github-mcp-server)
exactly — e.g. `search_repositories`, not an invented `search_repo`. Using
the real names is what lets live mode actually work against the real server
instead of failing with "unknown tool".

This is a lightweight, dependency-free intent parser (keyword/regex based)
rather than a live LLM call, so the whole project runs with zero API keys.
In a real deployment you'd swap `parse_intent` for an actual LLM call that
returns a structured tool-call (e.g. via function calling / tool_use) — the
important part for this project's *architecture* is that whatever produces
the tool_name/arguments still has to pass through the Supervisor before
anything executes. Nothing downstream trusts this agent's output blindly.

The real GitHub API requires `owner` and `repo` for almost every call. Since
this demo's intent parser has no memory of "which repo we're talking about",
it falls back to GITHUB_DEFAULT_OWNER / GITHUB_DEFAULT_REPO from .env unless
the message itself names one as "owner/repo".
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

DEFAULT_OWNER = os.getenv("GITHUB_DEFAULT_OWNER", "octocat")
DEFAULT_REPO = os.getenv("GITHUB_DEFAULT_REPO", "Hello-World")


@dataclass
class AgentDecision:
    is_tool_call: bool
    tool_name: Optional[str] = None
    arguments: dict[str, Any] = field(default_factory=dict)
    reply: str = ""


# Ordered: more specific / more dangerous intents first, so e.g. "merge pull
# request" doesn't get matched by a looser "pull request" pattern meant for creation.
# tool_name values are GitHub's REAL MCP tool names (github/github-mcp-server).
INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("merge_pull_request", re.compile(r"\bmerge\b.*\bpull request\b|\bmerge pr\b", re.I)),
    ("create_or_update_file", re.compile(r"\bpush\b.*\bmain\b|\bpush\b.*\bmaster\b|\bupdate\b.*\bfile\b", re.I)),
    ("create_release", re.compile(r"\b(create|cut|publish)\b.*\brelease\b", re.I)),
    ("create_pull_request", re.compile(r"\b(create|open|submit)\b.*\bpull request\b|\bpr\b", re.I)),
    ("create_branch", re.compile(r"\b(create|make)\b.*\bbranch\b", re.I)),
    ("add_issue_comment", re.compile(r"\bcomment\b.*\bissue\b", re.I)),
    ("create_issue", re.compile(r"\b(create|open|file)\b.*\bissue\b", re.I)),
    ("list_pull_requests", re.compile(r"\blist\b.*\bpull requests?\b|\bshow\b.*\bpull requests?\b", re.I)),
    ("get_issue", re.compile(r"\bget\b.*\bissue\b|\bshow\b.*\bissue\b", re.I)),
    ("search_code", re.compile(r"\bsearch\b.*\bcode\b", re.I)),
    ("search_repositories", re.compile(r"\bsearch\b.*\brepo(sitory|sitories)?\b|\bfind\b.*\brepo(sitory)?\b", re.I)),
    ("get_workflow_run", re.compile(r"\bworkflow\b.*\b(status|run)\b", re.I)),
]

TITLE_PATTERN = re.compile(r'titled?\s+"([^"]+)"|title[:=]\s*"([^"]+)"', re.I)
OWNER_REPO_PATTERN = re.compile(r"\b([\w.-]+)/([\w.-]+)\b")


def _extract_title(message: str, default: str) -> str:
    match = TITLE_PATTERN.search(message)
    if match:
        return next(g for g in match.groups() if g)
    return default


def _extract_owner_repo(message: str) -> tuple[str, str]:
    """Real GitHub tool calls need owner+repo. Look for an explicit
    'owner/repo' mention in the message; otherwise fall back to the
    configured default (see .env: GITHUB_DEFAULT_OWNER / GITHUB_DEFAULT_REPO)."""
    match = OWNER_REPO_PATTERN.search(message)
    if match:
        return match.group(1), match.group(2)
    return DEFAULT_OWNER, DEFAULT_REPO


def parse_intent(message: str) -> AgentDecision:
    for tool_name, pattern in INTENT_PATTERNS:
        if pattern.search(message):
            owner, repo = _extract_owner_repo(message)
            arguments: dict[str, Any] = {"owner": owner, "repo": repo}

            if tool_name in ("create_pull_request", "create_issue"):
                arguments["title"] = _extract_title(message, f"Auto-generated {tool_name}")
            if tool_name == "create_branch":
                branch_match = re.search(r"branch\s+(?:called|named)?\s*['\"]?([\w\-/]+)['\"]?", message, re.I)
                arguments["branch"] = branch_match.group(1) if branch_match else "new-feature-branch"
            if tool_name == "create_release":
                tag_match = re.search(r"\bv?\d+\.\d+(\.\d+)?\b", message)
                arguments["tag_name"] = tag_match.group(0) if tag_match else "v0.0.1"
            if tool_name in ("get_issue", "add_issue_comment"):
                num_match = re.search(r"#?(\d+)", message)
                arguments["issue_number"] = int(num_match.group(1)) if num_match else 1
            if tool_name in ("merge_pull_request",):
                num_match = re.search(r"#?(\d+)", message)
                arguments["pullNumber"] = int(num_match.group(1)) if num_match else 1
            if tool_name == "search_repositories":
                arguments = {"query": message}
            if tool_name == "search_code":
                arguments = {"query": message}
            if tool_name == "list_pull_requests":
                arguments = {"owner": owner, "repo": repo}
            if tool_name == "get_workflow_run":
                arguments = {"owner": owner, "repo": repo}

            return AgentDecision(is_tool_call=True, tool_name=tool_name, arguments=arguments)

    # No GitHub-tool intent matched — treat as plain conversation.
    return AgentDecision(
        is_tool_call=False,
        reply=(
            "I can help with GitHub actions (create/list issues, pull requests, branches, "
            "releases, workflow status) or general questions. What would you like to do? "
            "Mention 'owner/repo' if you don't want the default repo."
        ),
    )
