from __future__ import annotations

from typing import List

from ..models.base import AgentRequest, Message


def _collapse_user_prompt(messages: List[Message]) -> str:
    """Collapse user messages into a single prompt string.
    - Keep behavior minimal and deterministic.
    - Similar spirit to HF non-stream collapse in backends.
    """
    parts: List[str] = []
    for m in messages or []:
        role = m.get("role", "")
        if role == "user":
            content = m.get("content", "")
            if content:
                parts.append(content)
    return "\n".join(parts)


def _estimate_tokens(text: str) -> int:
    """Very rough token estimator, purposely simple.
    We avoid external dependencies; use whitespace word count.
    """
    if not text:
        return 0
    return len(text.split())


async def select_backend(request: AgentRequest) -> str:
    """Decide which backend to use: 'groq', 'gemini', or 'hf'.

    Priority order: force_backend > preferences.backend > heuristics > default 'groq'.

    Heuristics (Step 13):
    1) If tools_allowed has any tool -> 'groq'.
    2) If last user message length > 350 chars -> 'gemini'.
    3) If user says 'explain' OR 'analysis' in content -> 'gemini'.
    4) If asking info text under 200 chars AND no tools -> 'hf'.
    """
    prefs = (request or {}).get("preferences", {}) or {}
    force_backend = prefs.get("force_backend")
    if isinstance(force_backend, str) and force_backend.strip():
        return force_backend.strip()

    # Allow explicit backend preference when present (sanitized by API to avoid raw model override)
    preferred_backend = prefs.get("backend")
    if isinstance(preferred_backend, str) and preferred_backend.strip():
        return preferred_backend.strip()

    messages = (request or {}).get("messages", []) or []
    tools_allowed = (request or {}).get("tools_allowed", []) or []

    # Heuristic 1: any tool allowed -> groq
    if isinstance(tools_allowed, list) and len(tools_allowed) > 0:
        return "groq"

    # Get last user message content
    last_user_content = ""
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content"):
            last_user_content = str(m.get("content"))
            break

    lowered = last_user_content.lower()

    # Heuristic 2: long user message (>350 chars) -> gemini
    if len(last_user_content) > 350:
        return "gemini"

    # Heuristic 3: contains 'explain' or 'analysis' -> gemini
    if ("explain" in lowered) or ("analysis" in lowered):
        return "gemini"

    # Heuristic 4: information text under 200 chars AND no tools -> hf
    if len(last_user_content) > 0 and len(last_user_content) < 200 and (not tools_allowed):
        return "hf"

    # Default fallback
    return "groq"
