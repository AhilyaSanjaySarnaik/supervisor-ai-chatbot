"""
API-key authentication.

Every protected endpoint requires:
    Authorization: Bearer <api_key>

Each key is mapped (server-side, via .env) to a fixed role. This is what
actually closes the gap flagged in security review: previously a client
could put `"role": "admin"` in the request body and ABAC would just believe
it. Now the role comes from a secret key the server looks up — the request
body's role field, if present, is ignored and overwritten with the
authenticated role in main.py.

This is intentionally simple (static keys in .env, not JWT/OAuth/sessions)
for a self-contained project. See README for how you'd extend this to a
real identity provider (e.g. verifying a JWT from your org's SSO instead of
a static shared secret).
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException

from app.models.schemas import Role


def _load_key_map() -> dict[str, Role]:
    """Builds {api_key: role} from API_KEY_<ROLE> env vars, read fresh on
    every call so a key rotated in .env takes effect without a code change
    (still requires a server restart, same as every other .env value)."""
    mapping: dict[str, Role] = {}
    for role in Role:
        env_var = f"API_KEY_{role.value.upper()}"
        key = os.getenv(env_var)
        if key:
            mapping[key] = role
    return mapping


def get_current_role(authorization: Optional[str] = Header(default=None)) -> tuple[str, Role]:
    """FastAPI dependency. Validates the Authorization header and returns
    (api_key, role). Raises 401 if the header is missing/malformed or the
    key doesn't match any configured role."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header. Use: Authorization: Bearer <api_key>",
        )

    api_key = authorization.removeprefix("Bearer ").strip()
    key_map = _load_key_map()

    if not key_map:
        raise HTTPException(
            status_code=500,
            detail="No API keys configured on the server. Set API_KEY_GUEST / API_KEY_ANALYST / "
                   "API_KEY_DEVELOPER / API_KEY_ADMIN in .env.",
        )

    role = key_map.get(api_key)
    if role is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key, role