"""
FastAPI entry point. Deliberately thin — every route just validates input
(via Pydantic), authenticates the caller, and delegates to the orchestrator
or hitl_queue. No security logic lives here beyond that; the checkpoints
themselves stay in the Supervisor module.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.models.schemas import ApprovalDecision, ChatRequest, ChatResponse, Role  # noqa: E402
from app.supervisor import orchestrator  # noqa: E402
from app.supervisor.auth import get_current_role  # noqa: E402
from app.supervisor.hitl import hitl_queue  # noqa: E402

app = FastAPI(
    title="SupervisorGuard AI",
    description="A governed multi-agent chatbot that routes tool calls through a security supervisor before touching GitHub via MCP.",
    version="1.0.0",
)

# Permissive CORS since the frontend is a static file opened directly in the
# browser (file:// or any localhost port) for this demo — lock this down to
# specific origins before deploying anywhere real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    # Deliberately unauthenticated — no sensitive data, useful for uptime checks.
    return {"status": "ok", "mcp_mode": os.getenv("MCP_MODE", "mock")}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, auth: tuple[str, Role] = Depends(get_current_role)):
    _api_key, authenticated_role = auth
    # The authenticated role ALWAYS overrides whatever the client put in the
    # request body — closes the "just claim role: admin" gap. The body's
    # role field is kept in the schema only for backward-compat convenience;
    # it is never trusted for the actual permission decision.
    req.role = authenticated_role
    status, message, detail = orchestrator.handle_chat_request(req)
    return ChatResponse(request_id=os.urandom(4).hex(), status=status, message=message, detail=detail)


@app.get("/pending")
def list_pending(auth: tuple[str, Role] = Depends(get_current_role)):
    return [a.model_dump() for a in hitl_queue.list_pending()]


@app.post("/approve/{action_id}")
def approve(action_id: str, decision: ApprovalDecision, auth: tuple[str, Role] = Depends(get_current_role)):
    _api_key, authenticated_role = auth
    # Approving a queued high-risk action is itself a high-privilege act —
    # require the ADMIN role specifically, not just "any authenticated caller".
    if authenticated_role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Only an ADMIN-level API key can approve or deny pending actions")

    action = hitl_queue.decide(action_id, decision.approve)
    if action is None:
        raise HTTPException(status_code=404, detail="Pending action not found or already resolved")

    if not decision.approve:
        return {"action_id": action_id, "status": "denied", "note": decision.note}

    result = orchestrator.execute_approved_action(action)
    return {"action_id": action_id, "status": "approved", "result": result}


@app.get("/logs")
def get_logs(limit: int = 100, auth: tuple[str, Role] = Depends(get_current_role)):
    entries = orchestrator.security_log[-limit:]
    return [e.model_dump() for e in reversed(entries)]