from typing import List, Dict, Any
from .base import ChatBackend, Message
from ..utils.errors import ConfigError
from ..utils.logging import logger
import httpx
import asyncio

# On Windows/corporate environments, use OS trust store to avoid certifi mismatch
try:  # best-effort, dev-friendly
    import truststore  # type: ignore

    truststore.inject_into_ssl()
    logger.info("truststore: injected Windows certificate store for SSL")
except Exception:
    # Safe to ignore if unavailable; falls back to certifi
    pass

class HFBackend(ChatBackend):
    def __init__(self, api_base: str, api_key: str, model: str):
        # api_base is ignored when using InferenceClient; kept for signature compatibility
        if not api_key:
            raise ConfigError("HF_API_KEY required for HuggingFace backend")
        self.api_key = api_key
        self.model = model
        # Note: we use the OpenAI-compatible chat completions router; no local client needed.

    async def complete(self, messages: List[Message], **kwargs) -> str:
        # Collapse conversation into a single prompt for simple inference
        prompt = ""
        for m in messages:
            if m["role"] == "user":
                prompt += m["content"] + "\n"
            elif m["role"] == "system":
                prompt = m["content"] + "\n" + prompt
            elif m["role"] == "assistant":
                # ignore assistant content to reduce history cost
                pass

        temperature = kwargs.get("temperature", 0.7)
        max_new_tokens = min(int(kwargs.get("max_new_tokens", 256)), 1024)

        def _call():
            # Switch to HF OpenAI-compatible Chat Completions endpoint (serverless router).
            # Ref: https://huggingface.co/docs/inference-providers/index#alternative-openai-compatible-chat-completions-endpoint-chat-only
            url = "https://router.huggingface.co/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            # Minimal change: still collapse messages into a single user prompt.
            # This keeps our behavior consistent while using the chat endpoint.
            def do_request(model_id: str) -> Any:
                payload = {
                    "model": model_id,
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": float(temperature),
                    "max_tokens": int(max_new_tokens),
                    "stream": False,
                }
                with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
                    r = client.post(url, headers=headers, json=payload)
                    if r.status_code >= 400:
                        try:
                            logger.error("HF chat completions error %s for model %s: %s", r.status_code, model_id, r.text)
                        except Exception:
                            pass
                    r.raise_for_status()
                    return r.json()

            model_to_use = self.model
            try:
                data = do_request(model_to_use)
            except httpx.HTTPStatusError as e:
                # If model lacks provider selection and router rejects, retry with ':fastest'
                if e.response is not None and e.response.status_code == 400 and ":" not in model_to_use:
                    fallback_model = f"{model_to_use}:fastest"
                    logger.warning("Retrying HF chat with provider policy suffix ':fastest' -> %s", fallback_model)
                    data = do_request(fallback_model)
                else:
                    raise
            # OpenAI-format normalization
            if isinstance(data, dict):
                choices = data.get("choices")
                if isinstance(choices, list) and choices:
                    msg = choices[0].get("message") or {}
                    content = msg.get("content")
                    if isinstance(content, str):
                        return content
            # Fallback: stringify
            return str(data)

        try:
            result = await asyncio.to_thread(_call)
            # Some models may return dict-like in future; normalize to string
            if isinstance(result, str):
                return result
            return str(result)
        except Exception as e:
            logger.exception("HF Inference error: %s", e)
            raise

        
    async def stream(self, messages: List[Message], **kwargs):
        # Not implemented in v1.
        # Structured streaming will be considered after baseline stabilizes.
        raise NotImplementedError("HF streaming not supported yet")
