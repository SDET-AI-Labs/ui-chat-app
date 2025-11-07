from __future__ import annotations

import importlib
from typing import Callable, Dict, Any, Awaitable


ToolCallable = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


def get_tool(name: str) -> ToolCallable:
    """Dynamically import a tool module from this package and return its `run`.

    Only resolves modules under `chatstack.tools` by name, e.g. "echo" -> chatstack.tools.echo.
    The tool module must define: async def run(args: Dict[str, Any]) -> Dict[str, Any]
    """
    if not name or not isinstance(name, str):
        raise ValueError("tool name must be a non-empty string")

    module_name = f"{__name__}.{name}"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        raise ValueError(f"unknown tool: {name}") from e

    run_callable = getattr(module, "run", None)
    if run_callable is None or not callable(run_callable):
        raise ValueError(f"tool '{name}' is missing a callable 'run' function")

    return run_callable  # type: ignore[return-value]
