from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Any, TypedDict, Optional

Message = Dict[str, str]

class ChatBackend(ABC):
    @abstractmethod
    async def complete(self, messages: List[Message], **kwargs) -> str:
        ...

    @abstractmethod
    async def stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        ...


# ===== Agent Mode C: Backend Interface (Step 1 scaffold) =====
# NOTE: This is a minimal scaffold to be refined once Jack provides the
# final interface shape. Keep it backward-compatible and non-breaking.

class AgentRequest(TypedDict, total=False):
    """Input contract for the Agent pipeline (to be finalized).

    Fields (provisional):
    - messages: OpenAI-style messages: List[Message]
    - tools_allowed: optional list of tool names the agent may call
    - preferences: optional dict with flags (e.g., streaming_allowed, provider_hints)
    - metadata: optional opaque dict passed through for audit context
    """

    messages: List[Message]
    tools_allowed: List[str]
    preferences: Dict[str, Any]
    metadata: Dict[str, Any]


class AgentResponse(TypedDict, total=False):
    """Output contract for the Agent pipeline (to be finalized).

    Fields (provisional):
    - content: final assistant message content
    - used_model: the selected model identifier
    - used_tools: list of tool names that were executed (e.g., ["echo"])
    - timings: timing info per stage (selection, model, tools)
    - metadata: additional audit metadata
    - cost: tokens & approximate cost summary (e.g., tokens_in, tokens_out, approx_cost_in_$ or credits)
    """

    content: str
    used_model: str
    used_tools: List[str]
    timings: Dict[str, float]
    metadata: Dict[str, Any]
    cost: Dict[str, Any]
    # Optional screenshot path for tools like playwright_run (Step 14A)
    screenshot: str


class AgentBackend(ABC):
    """Agent Mode C backend interface.

    Responsibility:
    - Decide model backend (Groq / Gemini / HF) based on the request.
    - Optionally call approved tools via a registry.
    - Produce a final response and audit metadata.

    Final interface shape will be confirmed by Jack and may adjust the
    request/response fields. Keep implementations tolerant to extra keys.
    """

    @abstractmethod
    async def run(self, request: AgentRequest) -> AgentResponse:
        """Execute the agent pipeline and return the final response.

        Implementations should not perform destructive actions and must
        honor any `tools_allowed` constraints. For environments where
        streaming is requested, implementations may fallback to non-stream
        per backend capability (e.g., HF non-stream only).
        """
        ...
