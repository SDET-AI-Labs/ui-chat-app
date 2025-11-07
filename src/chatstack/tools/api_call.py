from __future__ import annotations

from typing import Any, Dict
import requests
from urllib.parse import urlparse


def _normalize_method(m: str | None) -> str:
    if not isinstance(m, str) or not m.strip():
        return "GET"
    return m.strip().upper()


async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        method = _normalize_method(args.get("method") if isinstance(args, dict) else None)
        url = args.get("url") if isinstance(args, dict) else None
        headers = args.get("headers") if isinstance(args, dict) else None
        body = args.get("body") if isinstance(args, dict) else None

        if not isinstance(url, str) or not url:
            return {"result": "error", "error": "missing url"}
        # Only allow http/https
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"result": "error", "error": "only http/https allowed"}

        if headers is not None and not isinstance(headers, dict):
            return {"result": "error", "error": "headers must be a dict"}
        if body is not None and not isinstance(body, dict):
            return {"result": "error", "error": "body must be a dict"}

        # Default JSON Content-Type for POST when no headers provided
        if method == "POST" and (headers is None):
            headers = {"Content-Type": "application/json"}

        # Make request
        try:
            resp = requests.request(method, url, headers=headers, json=body, timeout=30)
        except requests.RequestException as e:
            return {"result": "error", "error": str(e)}

        ct = resp.headers.get("content-type", "")
        if not (200 <= resp.status_code < 300):
            # Error case - non-2xx response
            body_text: str
            try:
                body_text = resp.text
            except Exception:
                body_text = ""
            if len(body_text) > 4000:
                body_text = body_text[:4000]
            return {
                "result": "error",
                "status_code": resp.status_code,
                "content_type": ct,
                "error": f"Request failed with status {resp.status_code}",
                "body": body_text
            }

        # Success case - attempt JSON parse first
        try:
            data = resp.json()
            return {
                "result": "success",
                "status_code": resp.status_code,
                "content_type": ct,
                "body": data
            }
        except ValueError:
            # Non-JSON response
            body_text: str
            try:
                body_text = resp.text
            except Exception:
                body_text = ""
            if len(body_text) > 2000:
                body_text = body_text[:2000]
            return {
                "result": "success",
                "status_code": resp.status_code,
                "content_type": ct,
                "body_text": body_text,
                "content_length": len(resp.content)
            }
    except Exception as e:
        return {"result": "error", "error": str(e)}
