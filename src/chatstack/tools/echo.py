from __future__ import annotations

from typing import Dict, Any


async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Echo tool: returns the provided text argument.

    Args:
        args: expects optional key "text" (str)
    Returns:
        {"result": str}
    """
    text = args.get("text", "") if isinstance(args, dict) else ""
    if not isinstance(text, str):
        text = str(text)
    return {"result": text}
