"""
Payload Sanitizer — first line of defense.

Pattern-matches user input for common prompt-injection and system-override
signatures BEFORE it reaches an LLM or a tool. This is deliberately cheap and
deterministic: it should reject obviously hostile input without needing a
model call, so the expensive/creative parts of the pipeline never even see it.

This is not a substitute for a trained classifier in production — see the
README's "Known limitations" section — but it stops the large majority of
naive injection attempts (the kind used in CTFs, demos, and most real-world
opportunistic attacks).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SanitizeResult:
    is_safe: bool
    matched_patterns: list[str]
    reason: str = ""


# Each pattern targets a category of attack. Keeping them named/grouped makes
# the security log human-readable ("blocked: instruction_override") instead
# of just "regex #7 matched".
INJECTION_PATTERNS: dict[str, re.Pattern] = {
    "instruction_override": re.compile(
        r"(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above|earlier)\s+"
        r"(instructions?|rules?|prompts?|context)",
        re.IGNORECASE,
    ),
    "role_hijack": re.compile(
        r"(you are now|act as|pretend to be|from now on you)\s+.{0,40}"
        r"(admin|root|developer|system|unrestricted|jailbreak)",
        re.IGNORECASE,
    ),
    "system_prompt_leak": re.compile(
        r"(reveal|show|print|repeat)\s+(your\s+)?(system\s+prompt|instructions|configuration)",
        re.IGNORECASE,
    ),
    "destructive_shell": re.compile(
        r"(rm\s+-rf|drop\s+table|delete\s+from\s+\w+\s+where\s+1\s*=\s*1|:(){:|:};?:)",
        re.IGNORECASE,
    ),
    "credential_exfiltration": re.compile(
        r"(dump|print|export|leak)\s+.{0,20}(secrets?|tokens?|credentials?|env(ironment)?\s*vars?|api\s*keys?)",
        re.IGNORECASE,
    ),
    "encoded_payload": re.compile(
        r"(base64|hex)\s*(decode|:)|(\\x[0-9a-f]{2}){4,}",
        re.IGNORECASE,
    ),
    "delimiter_escape": re.compile(
        r"(</?(system|user|assistant|instructions)>|```(system|end)?\s*$)",
        re.IGNORECASE,
    ),
}


def sanitize(payload: str) -> SanitizeResult:
    """
    Scan a raw text payload for injection signatures.

    Returns SanitizeResult(is_safe=False, ...) on the FIRST category matched
    so the caller always gets a clear, single reason to log and show the user
    rather than a noisy list of every heuristic that happened to fire.
    """
    if not payload or not payload.strip():
        return SanitizeResult(is_safe=False, matched_patterns=["empty_payload"], reason="Empty payload rejected")

    matched: list[str] = []
    for name, pattern in INJECTION_PATTERNS.items():
        if pattern.search(payload):
            matched.append(name)

    if matched:
        return SanitizeResult(
            is_safe=False,
            matched_patterns=matched,
            reason=f"Blocked: matched injection pattern(s) {', '.join(matched)}",
        )

    return SanitizeResult(is_safe=True, matched_patterns=[], reason="No injection signatures detected")
