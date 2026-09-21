"""
Pydantic data models shared across the API, supervisor, and agents.
Keeping these centralized means every layer validates against the same contract.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Role(str, Enum):
    GUEST = "guest"
    ANALYST = "analyst"
    DEVELOPER = "developer"
    ADMIN = "admin"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CheckpointResult(str, Enum):
    PASSED = "passed"
    BLOCKED = "blocked"
    QUEUED = "queued"


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Identifier of the human/user making the request")
    role: Role = Field(default=Role.GUEST)
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    request_id: str
    status: CheckpointResult
    message: str
    detail: Optional[dict[str, Any]] = None


class PendingAction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    role: Role
    tool_name: str
    arguments: dict[str, Any]
    reason: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending | approved | denied | expired


class ApprovalDecision(BaseModel):
    approver_id: str
    approve: bool
    note: Optional[str] = None


class LogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    role: Role
    checkpoint: str  # sanitizer | abac | hitl | execution
    result: CheckpointResult
    tool_name: Optional[str] = None
    detail: str = ""
