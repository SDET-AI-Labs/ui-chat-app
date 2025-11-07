"""Debug tools routes for server."""
from fastapi import APIRouter
from typing import Dict, List, Any
import inspect

router = APIRouter(prefix="/debug", tags=["debug"])

@router.get("/tools")
async def list_tools() -> Dict[str, Any]:
    """Return information about available tools."""
    from ..tools import get_tool
    from .. import tools
    
    tool_info = {}
    
    # Get all Python modules in the tools directory
    for name in dir(tools):
        if name.startswith('_'):
            continue
        try:
            # Get the tool function using get_tool
            tool_fn = get_tool(name)
            if tool_fn:
                # Get function signature and docstring
                sig = inspect.signature(tool_fn)
                doc = inspect.getdoc(tool_fn) or ""
                
                # Extract parameter info
                params = {}
                for param_name, param in sig.parameters.items():
                    param_info = {
                        "name": param_name,
                        "kind": str(param.kind),
                        "default": str(param.default) if param.default is not inspect.Parameter.empty else None,
                        "annotation": str(param.annotation) if param.annotation is not inspect.Parameter.empty else None
                    }
                    params[param_name] = param_info
                
                tool_info[name] = {
                    "name": name,
                    "doc": doc,
                    "parameters": params,
                    "return_type": str(sig.return_annotation) if sig.return_annotation is not inspect.Parameter.empty else None
                }
        except Exception as e:
            tool_info[name] = {
                "name": name,
                "error": str(e)
            }
    
    return {
        "tools": tool_info
    }