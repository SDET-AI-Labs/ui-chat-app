from typing import List, Dict, Any, AsyncIterator, Optional
import httpx
import json
from .base import ChatBackend, Message
from ..utils.errors import ConfigError
from ..utils.logging import logger
from ..settings import settings

"""
Gemini adapter (v1beta) with:
- non-streaming: generateContent
- streaming (structured): streamGenerateContent -> SSE-ish data chunks
We emit:
  - text deltas as {"type":"text_delta","text": "..."}
  - tool calls as {"type":"tool_call","name":"...","args":{...}}
  - safety/finish events as {"type":"meta","data":{...}}
Your API currently sends raw SSE with "data:" lines. We'll JSON-encode these dicts per chunk.
"""

def _to_gemini_contents(messages: List[Message]) -> Dict[str, Any]:
    # Convert OpenAI-like {role, content} -> Gemini "contents"
    # Gemini expects a sequence of role=USER/MODEL with "parts":[{"text": "..."}]
    contents: List[Dict[str, Any]] = []
    role_map = {"user": "user", "assistant": "model", "system": "user"}
    sys_prefix = ""
    for m in messages:
        role = role_map.get(m["role"], "user")
        text = m["content"]
        # Hoist system as a prefix into first user message to keep schema simple
        if m["role"] == "system":
            sys_prefix += text + "\n"
            continue
        if sys_prefix and role == "user":
            text = sys_prefix + text
            sys_prefix = ""
        contents.append({"role": role, "parts": [{"text": text}]})
    if sys_prefix:
        contents.append({"role": "user", "parts": [{"text": sys_prefix}]})
    return {"contents": contents}

class GeminiBackend(ChatBackend):
    def __init__(self, api_base: Optional[str], api_key: Optional[str], model: str):
        if not api_key:
            raise ConfigError("GEMINI_API_KEY is required for Gemini backend.")
        self.api_base = (api_base or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        self.api_key = api_key
        self.model = model
        # Step 6B: usage/cost placeholders captured from last response
        self.last_usage: Dict[str, Any] | None = None

    async def complete(self, messages: List[Message], **kwargs) -> str:
        url = f"{self.api_base}/models/{self.model}:generateContent?key={self.api_key}"
        body: Dict[str, Any] = _to_gemini_contents(messages)
        # temperature optional
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            body["generationConfig"] = {"temperature": kwargs["temperature"]}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        # Extract usage metadata -> standard usage dict
        try:
            um = data.get("usageMetadata", {}) if isinstance(data, dict) else {}
            # Correct field names per latest Gemini: promptTokenCount, candidatesTokenCount
            tin = um.get("promptTokenCount") if isinstance(um, dict) else None
            tout = um.get("candidatesTokenCount") if isinstance(um, dict) else None
            self.last_usage = {
                "tokens_in": int(tin) if isinstance(tin, int) else None,
                "tokens_out": int(tout) if isinstance(tout, int) else None,
                "approx_cost": None,
            }
        except Exception:
            self.last_usage = {"tokens_in": None, "tokens_out": None, "approx_cost": None}
        # Extract text from first candidate parts
        try:
            parts = data["candidates"][0]["content"]["parts"]
            texts: List[str] = []
            for p in parts:
                if "text" in p:
                    texts.append(p["text"])
                elif "inlineData" in p:
                    # ignore binaries for now
                    continue
                elif "functionCall" in p:
                    # If function call only, return a compact JSON
                    return json.dumps({"tool_call": p["functionCall"]})
            return "".join(texts) if texts else ""
        except Exception:
            logger.exception("Gemini bad response: %s", data)
            raise

    async def stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        """
        Structured streaming:
        We yield JSON strings, each representing an event:
          {"type":"text_delta","text": "..."}
          {"type":"tool_call","name":"...", "args":{...}}
          {"type":"meta","data":{...}}
          {"type":"done"}
        Caller (our API) will forward these as SSE data lines.
        """
        url = f"{self.api_base}/models/{self.model}:streamGenerateContent?key={self.api_key}"
        body: Dict[str, Any] = _to_gemini_contents(messages)
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            body["generationConfig"] = {"temperature": kwargs["temperature"]}

        async with httpx.AsyncClient(timeout=None) as client:
            headers = {"Accept": "text/event-stream"}
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                resp.raise_for_status()
                async for raw in resp.aiter_lines():
                    if not raw or not raw.startswith("data:"):
                        continue
                    chunk = raw[len("data:"):].strip()
                    if chunk == "[DONE]":
                        yield json.dumps({"type": "done"})
                        break
                    # Each chunk is a JSON object with partial candidates
                    try:
                        obj = json.loads(chunk)
                    except Exception:
                        continue
                    # Pass safety or metadata
                    if "promptFeedback" in obj or "usageMetadata" in obj:
                        # Capture usage when available
                        try:
                            um = obj.get("usageMetadata")
                            if isinstance(um, dict):
                                # Correct field names per latest Gemini
                                tin = um.get("promptTokenCount")
                                tout = um.get("candidatesTokenCount")
                                self.last_usage = {
                                    "tokens_in": int(tin) if isinstance(tin, int) else None,
                                    "tokens_out": int(tout) if isinstance(tout, int) else None,
                                    "approx_cost": None,
                                }
                        except Exception:
                            pass
                        yield json.dumps({"type": "meta", "data": obj})
                        continue
                    try:
                        cands = obj.get("candidates", [])
                        if not cands:
                            continue
                        parts = cands[0].get("content", {}).get("parts", [])
                        for p in parts:
                            # text delta
                            if "text" in p:
                                yield json.dumps({"type": "text_delta", "text": p["text"]})
                            # function/tool call (structured)
                            elif "functionCall" in p:
                                fc = p["functionCall"]
                                yield json.dumps({"type": "tool_call", "name": fc.get("name"), "args": fc.get("args", {})})
                            # other part kinds ignored for now
                    except Exception:
                        # If schema changes, don't crash the stream
                        continue
