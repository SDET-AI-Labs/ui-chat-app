from typing import List, Dict, Any, AsyncIterator
import httpx
from .base import ChatBackend, Message
from ..utils.errors import ConfigError

class OllamaBackend(ChatBackend):
    def __init__(self, base_url: str, model: str):
        if not base_url or not model:
            raise ConfigError("OLLAMA_BASE and OLLAMA_MODEL are required for Ollama backend.")
        self.base_url = base_url.rstrip('/')
        self.model = model

    async def complete(self, messages: List[Message], **kwargs) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": kwargs.get("temperature", 0.7)}
        }
        async with httpx.AsyncClient(timeout=None) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        return data.get("message", {}).get("content", "")

    async def stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": kwargs.get("temperature", 0.7)}
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        import json as _json
                        obj = _json.loads(line)
                        if "message" in obj and "content" in obj["message"]:
                            yield obj["message"]["content"]
                    except Exception:
                        continue
