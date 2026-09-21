import os

import pytest
from fastapi.testclient import TestClient

# Set test API keys BEFORE importing the app, since auth.py reads them from
# the environment at call time via os.getenv.
os.environ["API_KEY_GUEST"] = "test-guest-key"
os.environ["API_KEY_ANALYST"] = "test-analyst-key"
os.environ["API_KEY_DEVELOPER"] = "test-developer-key"
os.environ["API_KEY_ADMIN"] = "test-admin-key"

from app.main import app  # noqa: E402

client = TestClient(app)


def auth(role: str) -> dict:
    return {"Authorization": f"Bearer test-{role}-key"}


def test_health_is_unauthenticated():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_chat_without_auth_header_is_rejected():
    resp = client.post("/chat", json={"user_id": "u1", "role": "admin", "message": "hello"})
    assert resp.status_code == 401


def test_chat_with_invalid_key_is_rejected():
    resp = client.post(
        "/chat",
        json={"user_id": "u1", "role": "admin", "message": "hello"},
        headers={"Authorization": "Bearer not-a-real-key"},
    )
    assert resp.status_code == 401


def test_client_cannot_spoof_role_via_request_body():
    """The core fix: even if the client claims role=admin in the body, a
    guest-level key should still only get guest-level permissions."""
    resp = client.post(
        "/chat",
        json={"user_id": "attacker", "role": "admin", "message": 'create a pull request titled "x"'},
        headers=auth("guest"),
    )
    assert resp.status_code == 200
    # A guest key must NOT be able to create a pull request, no matter what
    # role the request body claims.
    assert resp.json()["status"] == "blocked"


def test_valid_key_grants_correct_role_access():
    resp = client.post(
        "/chat",
        json={"user_id": "u1", "role": "guest", "message": "search repositories for hello"},
        headers=auth("analyst"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "passed"


def test_pending_requires_auth():
    resp = client.get("/pending")
    assert resp.status_code == 401
    resp = client.get("/pending", headers=auth("guest"))
    assert resp.status_code == 200


def test_logs_requires_auth():
    resp = client.get("/logs")
    assert resp.status_code == 401
    resp = client.get("/logs", headers=auth("guest"))
    assert resp.status_code == 200


def test_only_admin_key_can_approve():
    # Queue a high-risk action as a developer first.
    chat_resp = client.post(
        "/chat",
        json={"user_id": "dev1", "role": "developer", "message": 'create a pull request titled "test"'},
        headers=auth("developer"),
    )
    action_id = chat_resp.json()["detail"]["action_id"]

    # A developer key (not admin) must be rejected.
    resp = client.post(
        f"/approve/{action_id}",
        json={"approver_id": "dev1", "approve": True},
        headers=auth("developer"),
    )
    assert resp.status_code == 403

    # An admin key must succeed.
    resp = client.post(
        f"/approve/{action_id}",
        json={"approver_id": "admin1", "approve": False},  # deny, to avoid a real side effect in this test
        headers=auth("admin"),
    )
    assert resp.status_code == 200