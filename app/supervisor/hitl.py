"""
Human-In-The-Loop (HITL) approval state machine.

High-risk tool calls are never executed automatically — they're written here
as a PendingAction and held until a human supervisor approves or denies them
via the dashboard (or they expire). This is the last line of defense: even if
sanitizer + ABAC both pass, a destructive action still requires a human.

State machine: pending -> approved | denied | expired
In-memory only, by design, for this demo — see README "Known limitations"
for what a production version needs (durable store, real auth on approvals).
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta
from typing import Optional

from app.models.schemas import PendingAction, Role

HITL_TIMEOUT_SECONDS = int(os.getenv("HITL_TIMEOUT_SECONDS", "900"))
HIGH_RISK_TOOLS = set(
    t.strip() for t in os.getenv(
        "HIGH_RISK_TOOLS",
        "create_pull_request,merge_pull_request,create_or_update_file,create_release",
    ).split(",") if t.strip()
)


class HITLQueue:
    """Thread-safe in-memory queue of pending human approvals."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingAction] = {}

    def requires_approval(self, tool_name: str) -> bool:
        return tool_name in HIGH_RISK_TOOLS

    def enqueue(self, user_id: str, role: Role, tool_name: str, arguments: dict, reason: str) -> PendingAction:
        action = PendingAction(
            user_id=user_id,
            role=role,
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
        )
        with self._lock:
            self._pending[action.id] = action
        return action

    def list_pending(self) -> list[PendingAction]:
        self._expire_stale()
        with self._lock:
            return [a for a in self._pending.values() if a.status == "pending"]

    def get(self, action_id: str) -> Optional[PendingAction]:
        with self._lock:
            return self._pending.get(action_id)

    def decide(self, action_id: str, approve: bool) -> Optional[PendingAction]:
        with self._lock:
            action = self._pending.get(action_id)
            if action is None or action.status != "pending":
                return None
            action.status = "approved" if approve else "denied"
            return action

    def _expire_stale(self) -> None:
        cutoff = datetime.utcnow() - timedelta(seconds=HITL_TIMEOUT_SECONDS)
        with self._lock:
            for action in self._pending.values():
                if action.status == "pending" and action.created_at < cutoff:
                    action.status = "expired"


# Module-level singleton — simplest possible shared state for a single-process demo.
hitl_queue = HITLQueue()
