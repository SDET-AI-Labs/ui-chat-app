import os
from typing import List, Dict, Any, AsyncIterator
import httpx
from .base import ChatBackend, Message
from ..utils.errors import ConfigError
from ..utils.logging import logger
from ..utils.schemas import ChatRequest

class OpenAILikeBackend(ChatBackend):
    def __init__(self, api_base: str, api_key: str, model: str, verify_ssl: bool = True):
        if not api_key:
            raise ConfigError("OPENAI_API_KEY is required for OpenAI-like backend.")
        self.api_base = api_base.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.verify_ssl = verify_ssl
        # Step 6A: usage/cost placeholders captured from last response
        self.last_usage: dict | None = None

    async def complete(self, messages: List[Message], **kwargs) -> str:
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=60, verify=self.verify_ssl) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        # Extract standard usage for Groq/OpenAI-compatible providers
        # Map to our standard dict: tokens_in, tokens_out, approx_cost(None)
        try:
            usage = data.get("usage", {}) if isinstance(data, dict) else {}
            prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
            completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
            self.last_usage = {
                "tokens_in": int(prompt_tokens) if isinstance(prompt_tokens, int) else None,
                "tokens_out": int(completion_tokens) if isinstance(completion_tokens, int) else None,
                "approx_cost": None,
            }
        except Exception:
            # Do not fail the request if usage is missing; leave None
            self.last_usage = {"tokens_in": None, "tokens_out": None, "approx_cost": None}

        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            logger.exception("Bad response: %s", data)
            raise

    async def stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=60, verify=self.verify_ssl) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[len("data:"):].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = httpx.Response(200, json=None)
                    except Exception:
                        pass
                    try:
                        import json as _json
                        delta = _json.loads(chunk)["choices"][0]["delta"]
                        if "content" in delta:
                            yield delta["content"]
                    except Exception:
                        continue
