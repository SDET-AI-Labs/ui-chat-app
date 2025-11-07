from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse
from sse_starlette.sse import EventSourceResponse
from .debug import router as debug_router
from typing import AsyncIterator, Dict, Any, List, cast, Optional
import asyncio
import json
from pydantic import BaseModel, Field, EmailStr
import re
import os
import logging
from dotenv import load_dotenv
from ..utils.schemas import ChatRequest, Message as ChatMessage
from ..utils.logging import logger
from ..utils.errors import ConfigError
from ..settings import settings
from ..models import OpenAILikeBackend, OllamaBackend, ChatBackend, GeminiBackend, HFBackend
from ..store.sqlite import append_messages
from ..models.base import AgentRequest as AgentReqTyped, AgentResponse as AgentRespTyped
from ..agent.model_selector import select_backend
from ..tools import get_tool
from ..cost.cost_utils import compute_cost
from ..store.agent_audit import insert_agent_request, list_agent_requests




# Ensure db_query logs are visible in the terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("db_query").setLevel(logging.INFO)

# Load .env file so all env vars are available to tools
load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=True)

app = FastAPI(title="ChatStack")
app.include_router(debug_router)

# Debug log: print which .env file path was loaded
try:
    env_file = getattr(settings, 'model_config', {}).get('env_file', None)
    logger.info(f"[startup] settings.env_file: {env_file} (cwd={os.getcwd()})")
except Exception as e:
    logger.warning(f"[startup] Could not determine .env file path: {e}")

def get_backend() -> ChatBackend:
    if settings.backend == "openai_like":
        return OpenAILikeBackend(
            settings.openai_api_base,
            cast(str, settings.openai_api_key),
            settings.openai_model,
            verify_ssl=settings.openai_verify_ssl,
        )
    elif settings.backend == "ollama":
        return OllamaBackend(settings.ollama_base, settings.ollama_model)
    elif settings.backend == "gemini":
        return GeminiBackend(settings.gemini_api_base, settings.gemini_api_key, settings.gemini_model)
    elif settings.backend == "hf":
        return HFBackend(
            settings.hf_api_base,
            cast(str, settings.hf_api_key),
            settings.hf_model,
        )

    else:
        raise ConfigError(f"Unsupported backend: {settings.backend}")


def get_backend_by_name(name: str) -> ChatBackend:
    """Resolve a backend instance by logical name used in ModelSelector.
    Supported: "groq" -> OpenAILikeBackend, "gemini" -> GeminiBackend, "hf" -> HFBackend.
    """
    n = (name or "").lower().strip()
    if n == "groq":
        return OpenAILikeBackend(
            settings.openai_api_base,
            cast(str, settings.openai_api_key),
            settings.openai_model,
            verify_ssl=settings.openai_verify_ssl,
        )
    if n == "gemini":
        return GeminiBackend(settings.gemini_api_base, settings.gemini_api_key, settings.gemini_model)
    if n == "hf":
        return HFBackend(settings.hf_api_base, cast(str, settings.hf_api_key), settings.hf_model)
    raise ConfigError(f"Unsupported selected backend: {name}")

class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr

@app.post("/users/validate/{validation_type}")
async def validate_user_input(validation_type: str, body: Optional[Dict[str, Any]] = Body(default=None)):
    """Validation endpoints for user creation tests."""
    
    # Test case 1: Invalid type validation
    if validation_type == "number":
        if not body or not isinstance(body.get("name"), str):
            raise HTTPException(
                status_code=400,
                detail="Invalid input: name must be a string"
            )
        return {"message": "Validation passed"}
            
    # Test case 2: Empty body validation
    elif validation_type == "empty":
        if not body:
            raise HTTPException(
                status_code=400,
                detail="Request body cannot be empty"
            )
        return {"message": "Validation passed"}
    
    # Test case 3: Boolean type validation
    elif validation_type == "boolean":
        if not body or not isinstance(body.get("name"), str):
            raise HTTPException(
                status_code=400,
                detail="Invalid input: name must be a string"
            )
        return {"message": "Validation passed"}
    
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown validation type: {validation_type}"
        )

@app.get("/health")
async def health():
    return {"status": "ok", "backend": settings.backend}

@app.get("/debug/settings")
async def debug_settings():
    return {
        "backend": settings.backend,
        "openai_api_base": settings.openai_api_base,
        "openai_model": settings.openai_model,
        "openai_verify_ssl": settings.openai_verify_ssl,
        "has_openai_key": bool(settings.openai_api_key),
        "db_kind": settings.db_kind,
        "db_string": settings.db_string,
    }

@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        backend = get_backend()
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    content = await backend.complete([m.model_dump() for m in req.messages], temperature=req.temperature)
    session_id = req.session_id or "default"
    # persist user + assistant last turn
    if req.messages:
        append_messages(session_id, [(req.messages[-1].role, req.messages[-1].content), ("assistant", content)])
    return {"role": "assistant", "content": content}

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    try:
        backend = get_backend()
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def gen():
        gen_iter: AsyncIterator[str] = backend.stream([m.model_dump() for m in req.messages], temperature=req.temperature)  # type: ignore[assignment]
        async for chunk in gen_iter:
            yield {"data": chunk}
        yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(gen())


# ===== Agent Mode C: Step 4 - /agent endpoint (skeleton, no tools/streaming) =====
class AgentApiRequest(BaseModel):
    messages: List[ChatMessage]
    preferences: Dict[str, Any] | None = None
    tools_allowed: List[str] | None = None


@app.post("/agent")
async def agent_endpoint(req: AgentApiRequest):
    # Utility: parse a direct tool invocation syntax in the latest user message.
    # Supported formats:
    #   "tool: name {json_args}"
    #   "tool:name {json_args}"
    #   "tool name {json_args}" (space-separated)
    def _parse_direct_tool(msg: ChatMessage) -> Dict[str, Any] | None:
        try:
            if msg.role != "user" or not msg.content:
                return None
            text = msg.content.strip()
            # quick check
            if not text.lower().startswith("tool"):
                return None
            # normalize prefixes
            m = re.match(r"^tool\s*[:]?\s*([a-zA-Z0-9_\-]+)(?:\s+(\{.*\}))?\s*$", text, re.DOTALL)
            if not m:
                return None
            name = m.group(1)
            args_raw = m.group(2) or "{}"
            try:
                args = json.loads(args_raw)
            except Exception:
                args = {}
            return {"name": name, "args": args}
        except Exception:
            return None

    # Utility: attempt to extract a tool_call JSON object from model content.
    # Expects content to be a JSON string like {"tool_call": {"name":..., "args": {...}}}
    def _extract_tool_call_from_content(content: str) -> Dict[str, Any] | None:
        try:
            obj = json.loads((content or "").strip())
            if isinstance(obj, dict) and "tool_call" in obj:
                tc = obj.get("tool_call")
                if isinstance(tc, dict) and tc.get("name"):
                    args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                    return {"name": str(tc["name"]), "args": args}
        except Exception:
            pass
        return None

    # Utility: extract simple tool schema {"tool":"name","args":{...}}
    def _extract_simple_tool(content: str) -> Dict[str, Any] | None:
        try:
            raw = (content or "").strip()
            # Strip fenced code block markers if present: ```json ... ``` or ``` ... ```
            if raw.startswith("```"):
                # Remove opening fence line
                lines = raw.splitlines()
                if lines:
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    # Remove trailing fence if last line starts with ```
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                raw = "\n".join(lines).strip()
            obj = json.loads(raw)
            if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
                name = str(obj.get("tool")).strip()
                args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
                return {"name": name, "args": args}
        except Exception:
            pass
        return None

    # Utility: extract embedded tool JSON inside arbitrary text/code (e.g., Python fences)
    def _extract_embedded_tool_json(content: str) -> Dict[str, Any] | None:
        raw = (content or "")
        # Quick scan for '"tool"'
        idx = raw.find('"tool"')
        while idx != -1:
            # find a preceding '{'
            start = raw.rfind('{', 0, idx)
            if start == -1:
                screenshot_path: str | None = None
                idx = raw.find('"tool"', idx + 6)
                continue
            # brace matching scan forward
            depth = 0
            in_str = False
            esc = False
            end = None
            for j in range(start, len(raw)):
                c = raw[j]
                if in_str:
                    if esc:
                        esc = False
                    elif c == '\\':
                        esc = True
                    elif c == '"':
                        in_str = False
                else:
                    if c == '"':
                        in_str = True
                    elif c == '{':
                        depth += 1
                    elif c == '}':
                        if depth > 0:
                            depth -= 1
                        if depth == 0:
                            end = j + 1
                            break
            if end is not None:
                chunk = raw[start:end].strip()
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
                        name = str(obj.get("tool")).strip()
                        args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
                        return {"name": name, "args": args}
                except Exception:
                    pass
            idx = raw.find('"tool"', idx + 6)
        return None
    
    # 1) Construct AgentRequest object (as plain dict matching TypedDict)
    # Sanitize preferences: disallow any raw model override hints.
    raw_prefs = dict(req.preferences or {})
    if raw_prefs:
        # Drop keys like 'model', 'openai_model', 'hf_model', 'gemini_model', 'ollama_model', and any '*_model'.
        # Allow 'backend' and 'force_backend'.
        blocked_keys = {"model", "openai_model", "hf_model", "gemini_model", "ollama_model"}
        to_delete = set()
        for k in list(raw_prefs.keys()):
            if (k in blocked_keys or k.endswith("_model")) and k not in {"backend", "force_backend"}:
                to_delete.add(k)
        for k in to_delete:
            raw_prefs.pop(k, None)

    agent_request: AgentReqTyped = {
        "messages": [m.model_dump() for m in req.messages],
        "preferences": raw_prefs,
        "tools_allowed": list(req.tools_allowed or []),
        "metadata": {},
    }

    # Track executed tools by name only
    used_tools: List[str] = []
    screenshot_path: str | None = None
    meta_extra: Dict[str, Any] = {}

    # 2) If user explicitly requested a tool and it's allowed, run it directly and return.
    last_msg = req.messages[-1] if req.messages else None
    direct_tc = _parse_direct_tool(last_msg) if last_msg else None
    if direct_tc and direct_tc.get("name"):
        tool_name = str(direct_tc["name"]).strip()
        if req.tools_allowed and tool_name in req.tools_allowed:
            try:
                tool_fn = get_tool(tool_name)
                tool_out = await tool_fn(direct_tc.get("args") or {})
                if isinstance(tool_out, dict) and tool_out.get("result") == "error":
                    try:
                        logger.warning("tool %s error: %s", tool_name, tool_out.get("error"))
                    except Exception:
                        pass
                    try:
                        err = tool_out.get("error")
                        if isinstance(err, str):
                            meta_extra["tool_error"] = err
                        meta_extra["tool"] = tool_name
                        dep = tool_out.get("dependency")
                        if isinstance(dep, str):
                            meta_extra["dependency"] = dep
                        hint = tool_out.get("install_hint")
                        if isinstance(hint, str):
                            meta_extra["install_hint"] = hint
                    except Exception:
                        pass
                used_tools = [tool_name]
                # Return a concise content summarizing the tool result.
                display = json.dumps(tool_out)[:800]
                resp: AgentRespTyped = {
                    "content": f"Tool '{tool_name}' executed successfully. Result: {display}",
                    "used_model": "tools-only",
                    "used_tools": used_tools,
                    "cost": {"tokens_in": None, "tokens_out": None, "approx_cost": None},
                    "timings": {},
                    "metadata": {"tool_trigger": "direct"},
                }
                if isinstance(tool_out, dict) and isinstance(tool_out.get("screenshot"), str):
                    resp["screenshot"] = cast(str, tool_out.get("screenshot"))
                # attach tool error diagnostics if any
                try:
                    if meta_extra:
                        md = resp.get("metadata") or {}
                        if isinstance(md, dict):
                            md.update(meta_extra)
                            resp["metadata"] = md
                except Exception:
                    pass
                return resp
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"tool '{tool_name}' failed: {e}")
        else:
            raise HTTPException(status_code=403, detail=f"tool '{tool_name}' not allowed")

    # 3) Otherwise, select backend via ModelSelector (deterministic rules)
    backend_name = await select_backend(agent_request)

    # 4) Resolve backend instance like /chat (reuse settings)
    try:
        backend = get_backend_by_name(backend_name)
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 5) Call backend.complete once
    content = await backend.complete(agent_request["messages"], temperature=0.7)

    # 6) If the model requested a tool via structured JSON, honor it when allowed
    # 6a) Simple schema: {"tool":"echo|run_pytest","args":{...}}
    st = _extract_simple_tool(content)
    if st and st.get("name") and (req.tools_allowed and st["name"] in req.tools_allowed):
        tool_name = st["name"]
        if tool_name == "echo":
            try:
                tool_fn = get_tool("echo")
                tool_out = await tool_fn(st.get("args") or {})
                if isinstance(tool_out, dict) and "result" in tool_out:
                    content = str(tool_out.get("result"))
                else:
                    content = json.dumps(tool_out)
                used_tools = ["echo"]
            except Exception:
                pass
        elif tool_name == "run_pytest":
            try:
                tool_fn = get_tool("run_pytest")
                tool_out = await tool_fn(st.get("args") or {})
                exit_code = int(tool_out.get("exit_code", 0)) if isinstance(tool_out, dict) else 0
                if exit_code == 127:
                    content = "pytest not installed in environment"
                elif isinstance(tool_out, dict) and (tool_out.get("no_tests") or tool_out.get("collected") == 0):
                    content = "no tests collected"
                else:
                    passed = 0 if not isinstance(tool_out, dict) else int(tool_out.get("passed", 0) or 0)
                    failed = 0 if not isinstance(tool_out, dict) else int(tool_out.get("failed", 0) or 0)
                    skipped = 0 if not isinstance(tool_out, dict) else int(tool_out.get("skipped", 0) or 0)
                    content = f"passed: {passed}, failed: {failed}, skipped: {skipped}"
                used_tools = ["run_pytest"]
            except Exception:
                pass
        elif tool_name == "playwright_run":
            try:
                tool_fn = get_tool("playwright_run")
                tool_out = await tool_fn(st.get("args") or {})
                if isinstance(tool_out, dict):
                    if tool_out.get("result") == "error" and isinstance(tool_out.get("error"), str):
                        try:
                            logger.warning("tool playwright_run error: %s", tool_out.get("error"))
                        except Exception:
                            pass
                        try:
                            meta_extra["tool"] = "playwright_run"
                            meta_extra["tool_error"] = cast(str, tool_out.get("error"))
                            dep = tool_out.get("dependency")
                            if isinstance(dep, str):
                                meta_extra["dependency"] = dep
                            hint = tool_out.get("install_hint")
                            if isinstance(hint, str):
                                meta_extra["install_hint"] = hint
                        except Exception:
                            pass
                        content = f"error: {tool_out.get('error')}"
                    elif "result" in tool_out:
                        content = str(tool_out.get("result"))
                    else:
                        content = json.dumps(tool_out)
                    if isinstance(tool_out.get("screenshot"), str):
                        screenshot_path = cast(str, tool_out.get("screenshot"))
                else:
                    content = json.dumps(tool_out)
                used_tools = ["playwright_run"]
            except Exception:
                pass
        elif tool_name == "db_query":
            try:
                tool_fn = get_tool("db_query")
                tool_out = await tool_fn(st.get("args") or {})
                # Expect tool_out.result to be list of rows or 'error'
                if isinstance(tool_out, dict):
                    if tool_out.get("result") == "error":
                        err = tool_out.get("error")
                        content = f"error: {err}" if isinstance(err, str) else json.dumps(tool_out)
                        try:
                            meta_extra["tool"] = "db_query"
                            if isinstance(err, str):
                                meta_extra["tool_error"] = err
                        except Exception:
                            pass
                    else:
                        content = json.dumps(tool_out.get("result"))
                else:
                    content = json.dumps(tool_out)
                used_tools = ["db_query"]
            except Exception:
                pass
        elif tool_name == "excel_read":
            try:
                tool_fn = get_tool("excel_read")
                tool_out = await tool_fn(st.get("args") or {})
                if isinstance(tool_out, dict):
                    if tool_out.get("result") == "error":
                        err = tool_out.get("error")
                        content = f"error: {err}" if isinstance(err, str) else json.dumps(tool_out)
                        try:
                            meta_extra["tool"] = "excel_read"
                            if isinstance(err, str):
                                meta_extra["tool_error"] = err
                        except Exception:
                            pass
                    else:
                        content = json.dumps(tool_out.get("result"))
                else:
                    content = json.dumps(tool_out)
                used_tools = ["excel_read"]
            except Exception:
                pass
        elif tool_name == "test_from_excel":
            try:
                tool_fn = get_tool("test_from_excel")
                tool_out = await tool_fn(st.get("args") or {})
                content = json.dumps(tool_out)
                used_tools = ["test_from_excel"]
            except Exception:
                pass
        elif tool_name == "api_call":
            try:
                tool_fn = get_tool("api_call")
                tool_out = await tool_fn(st.get("args") or {})
                if isinstance(tool_out, dict) and tool_out.get("result") == "error":
                    # keep structured error minimal in content
                    err = tool_out.get("error")
                    sc = tool_out.get("status_code")
                    if isinstance(err, str):
                        content = f"error: {err}"
                    elif sc is not None:
                        content = json.dumps({"status_code": sc, "body": tool_out.get("body")})
                    else:
                        content = json.dumps(tool_out)
                    try:
                        meta_extra["tool"] = "api_call"
                        if isinstance(err, str):
                            meta_extra["tool_error"] = err
                    except Exception:
                        pass
                else:
                    content = json.dumps(tool_out.get("result") if isinstance(tool_out, dict) else tool_out)
                used_tools = ["api_call"]
            except Exception:
                pass
    else:
        # Fallback: if content parses to JSON without 'tool' but only 'args' and single allowed run_pytest
        try:
            raw = (content or "").strip()
            if raw.startswith("```"):
                lines = raw.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()
            obj = json.loads(raw)
            if (
                isinstance(obj, dict)
                and "tool" not in obj
                and "args" in obj
                and req.tools_allowed == ["run_pytest"]
            ):
                try:
                    tool_fn = get_tool("run_pytest")
                    args_val = obj.get("args")
                    # Accept list or dict; normalize
                    call_args = args_val if isinstance(args_val, dict) else {}
                    tool_out = await tool_fn(call_args)
                    passed = 0 if not isinstance(tool_out, dict) else int(tool_out.get("passed", 0) or 0)
                    failed = 0 if not isinstance(tool_out, dict) else int(tool_out.get("failed", 0) or 0)
                    skipped = 0 if not isinstance(tool_out, dict) else int(tool_out.get("skipped", 0) or 0)
                    content = f"passed: {passed}, failed: {failed}, skipped: {skipped}"
                    used_tools = ["run_pytest"]
                except Exception:
                    pass
        except Exception:
            pass
        # Fallback 2: embedded tool JSON anywhere in the content (e.g., code blocks)
        if not used_tools:
            et = _extract_embedded_tool_json(content)
            if et and et.get("name") and (req.tools_allowed and et["name"] in req.tools_allowed):
                if et["name"] == "echo":
                    try:
                        tool_fn = get_tool("echo")
                        tool_out = await tool_fn(et.get("args") or {})
                        content = str(tool_out.get("result")) if isinstance(tool_out, dict) and "result" in tool_out else json.dumps(tool_out)
                        used_tools = ["echo"]
                    except Exception:
                        pass
                elif et["name"] == "run_pytest":
                    try:
                        tool_fn = get_tool("run_pytest")
                        tool_out = await tool_fn(et.get("args") or {})
                        exit_code = int(tool_out.get("exit_code", 0)) if isinstance(tool_out, dict) else 0
                        if exit_code == 127:
                            content = "pytest not installed in environment"
                        elif isinstance(tool_out, dict) and (tool_out.get("no_tests") or tool_out.get("collected") == 0):
                            content = "no tests collected"
                        else:
                            passed = 0 if not isinstance(tool_out, dict) else int(tool_out.get("passed", 0) or 0)
                            failed = 0 if not isinstance(tool_out, dict) else int(tool_out.get("failed", 0) or 0)
                            skipped = 0 if not isinstance(tool_out, dict) else int(tool_out.get("skipped", 0) or 0)
                            content = f"passed: {passed}, failed: {failed}, skipped: {skipped}"
                        used_tools = ["run_pytest"]
                    except Exception:
                        pass
                elif et["name"] == "playwright_run":
                    try:
                        tool_fn = get_tool("playwright_run")
                        tool_out = await tool_fn(et.get("args") or {})
                        if isinstance(tool_out, dict):
                            if tool_out.get("result") == "error" and isinstance(tool_out.get("error"), str):
                                try:
                                    logger.warning("tool playwright_run error: %s", tool_out.get("error"))
                                except Exception:
                                    pass
                                try:
                                    meta_extra["tool"] = "playwright_run"
                                    meta_extra["tool_error"] = cast(str, tool_out.get("error"))
                                    dep = tool_out.get("dependency")
                                    if isinstance(dep, str):
                                        meta_extra["dependency"] = dep
                                    hint = tool_out.get("install_hint")
                                    if isinstance(hint, str):
                                        meta_extra["install_hint"] = hint
                                except Exception:
                                    pass
                                content = f"error: {tool_out.get('error')}"
                            elif "result" in tool_out:
                                content = str(tool_out.get("result"))
                            else:
                                content = json.dumps(tool_out)
                            if isinstance(tool_out.get("screenshot"), str):
                                screenshot_path = cast(str, tool_out.get("screenshot"))
                        else:
                            content = json.dumps(tool_out)
                        used_tools = ["playwright_run"]
                    except Exception:
                        pass
                elif et["name"] == "db_query":
                    try:
                        tool_fn = get_tool("db_query")
                        tool_out = await tool_fn(et.get("args") or {})
                        if isinstance(tool_out, dict) and tool_out.get("result") == "error":
                            err = tool_out.get("error")
                            content = f"error: {err}" if isinstance(err, str) else json.dumps(tool_out)
                            try:
                                meta_extra["tool"] = "db_query"
                                if isinstance(err, str):
                                    meta_extra["tool_error"] = err
                            except Exception:
                                pass
                        else:
                            content = json.dumps(tool_out.get("result") if isinstance(tool_out, dict) else tool_out)
                        used_tools = ["db_query"]
                    except Exception:
                        pass
                elif et["name"] == "excel_read":
                    try:
                        tool_fn = get_tool("excel_read")
                        tool_out = await tool_fn(et.get("args") or {})
                        if isinstance(tool_out, dict) and tool_out.get("result") == "error":
                            err = tool_out.get("error")
                            content = f"error: {err}" if isinstance(err, str) else json.dumps(tool_out)
                            try:
                                meta_extra["tool"] = "excel_read"
                                if isinstance(err, str):
                                    meta_extra["tool_error"] = err
                            except Exception:
                                pass
                        else:
                            content = json.dumps(tool_out.get("result") if isinstance(tool_out, dict) else tool_out)
                        used_tools = ["excel_read"]
                    except Exception:
                        pass
                elif et["name"] == "test_from_excel":
                    try:
                        tool_fn = get_tool("test_from_excel")
                        tool_out = await tool_fn(et.get("args") or {})
                        content = json.dumps(tool_out)
                        used_tools = ["test_from_excel"]
                    except Exception:
                        pass
                elif et["name"] == "api_call":
                    try:
                        tool_fn = get_tool("api_call")
                        tool_out = await tool_fn(et.get("args") or {})
                        if isinstance(tool_out, dict) and tool_out.get("result") == "error":
                            err = tool_out.get("error")
                            sc = tool_out.get("status_code")
                            if isinstance(err, str):
                                content = f"error: {err}"
                            elif sc is not None:
                                content = json.dumps({"status_code": sc, "body": tool_out.get("body")})
                            else:
                                content = json.dumps(tool_out)
                            try:
                                meta_extra["tool"] = "api_call"
                                if isinstance(err, str):
                                    meta_extra["tool_error"] = err
                            except Exception:
                                pass
                        else:
                            content = json.dumps(tool_out.get("result") if isinstance(tool_out, dict) else tool_out)
                        used_tools = ["api_call"]
                    except Exception:
                        pass

    # 6b) Legacy schema: {"tool_call": {"name":..., "args": {...}}}
    tc = _extract_tool_call_from_content(content)
    if tc and tc.get("name") and (req.tools_allowed and tc["name"] in req.tools_allowed):  # Check tool call
        try:
            tool_fn = get_tool(tc["name"])  # type: ignore[arg-type]
            tool_out = await tool_fn(tc.get("args") or {})
            # For run_pytest, replace with concise summary; for others keep existing behavior
            if tc["name"] == "run_pytest":
                exit_code = int(tool_out.get("exit_code", 0)) if isinstance(tool_out, dict) else 0
                if exit_code == 127:
                    content = "pytest not installed in environment"
                elif isinstance(tool_out, dict) and (tool_out.get("no_tests") or tool_out.get("collected") == 0):
                    content = "no tests collected"
                else:
                    passed = 0 if not isinstance(tool_out, dict) else int(tool_out.get("passed", 0) or 0)
                    failed = 0 if not isinstance(tool_out, dict) else int(tool_out.get("failed", 0) or 0)
                    skipped = 0 if not isinstance(tool_out, dict) else int(tool_out.get("skipped", 0) or 0)
                    content = f"passed: {passed}, failed: {failed}, skipped: {skipped}"
                used_tools = ["run_pytest"]
            elif tc["name"] == "playwright_run":
                if isinstance(tool_out, dict):
                    if tool_out.get("result") == "error" and isinstance(tool_out.get("error"), str):
                        try:
                            logger.warning("tool playwright_run error: %s", tool_out.get("error"))
                        except Exception:
                            pass
                        try:
                            meta_extra["tool"] = "playwright_run"
                            meta_extra["tool_error"] = cast(str, tool_out.get("error"))
                            dep = tool_out.get("dependency")
                            if isinstance(dep, str):
                                meta_extra["dependency"] = dep
                            hint = tool_out.get("install_hint")
                            if isinstance(hint, str):
                                meta_extra["install_hint"] = hint
                        except Exception:
                            pass
                        content = f"error: {tool_out.get('error')}"
                    elif "result" in tool_out:
                        content = str(tool_out.get("result"))
                    else:
                        content = json.dumps(tool_out)
                    if isinstance(tool_out.get("screenshot"), str):
                        screenshot_path = cast(str, tool_out.get("screenshot"))
                else:
                    content = json.dumps(tool_out)
                used_tools = ["playwright_run"]
            elif tc["name"] == "db_query":
                # Legacy tool_call support
                used_tools = ["db_query"]
                if isinstance(tool_out, dict) and tool_out.get("result") == "error":
                    err = tool_out.get("error")
                    content = f"error: {err}" if isinstance(err, str) else json.dumps(tool_out)
                    try:
                        meta_extra["tool"] = "db_query"
                        if isinstance(err, str):
                            meta_extra["tool_error"] = err
                    except Exception:
                        pass
                else:
                    content = json.dumps(tool_out.get("result") if isinstance(tool_out, dict) else tool_out)
            else:
                used_tools = [tc["name"]]
                # If content was just the tool_call JSON, replace with a friendly summary
                try:
                    obj = json.loads(content)
                    if isinstance(obj, dict) and list(obj.keys()) == ["tool_call"]:
                        content = f"Tool '{tc['name']}' executed. Result: {json.dumps(tool_out)[:800]}"
                except Exception:
                    pass
        except Exception:
            # On failure, leave content and used_tools unchanged
            pass

    # 7) Build cost info from backend usage (Step 6A for Groq/OpenAI-like only)
    cost_info: Dict[str, Any] = {"tokens_in": None, "tokens_out": None, "approx_cost": None}
    try:
        usage = getattr(backend, "last_usage", None)
        if isinstance(usage, dict):
            # Expect keys: tokens_in, tokens_out, approx_cost
            tin = usage.get("tokens_in")
            tout = usage.get("tokens_out")
            cost_info["tokens_in"] = int(tin) if isinstance(tin, int) else None
            cost_info["tokens_out"] = int(tout) if isinstance(tout, int) else None
    except Exception:
        pass

    # Step 6C: For HF fallback, if tokens are missing, estimate from prompt/output.
    if backend_name == "hf" and (cost_info["tokens_in"] is None or cost_info["tokens_out"] is None):
        try:
            # Collapse prompt from user messages only
            prompt_parts: List[str] = []
            for m in agent_request["messages"]:
                if (m.get("role") == "user") and m.get("content"):
                    prompt_parts.append(str(m.get("content")))
            prompt_text = "\n".join(prompt_parts)
            est_in = int(round(len(prompt_text) / 4.0))
            est_out = int(round(len(content or "") / 4.0))
            cost_info["tokens_in"] = est_in
            cost_info["tokens_out"] = est_out
        except Exception:
            # Leave as None if estimation fails
            pass

    # Compute approx_cost when we have integers for tokens
    try:
        ti = cost_info["tokens_in"]
        to = cost_info["tokens_out"]
        if isinstance(ti, int) and isinstance(to, int):
            # Narrow type for static checkers; runtime value is from selector
            bn = backend_name if backend_name in ("groq", "gemini", "hf") else "hf"
            cost_info["approx_cost"] = compute_cost(bn, ti, to)
    except Exception:
        pass

    # Return AgentResponse shape with cost/timings/metadata
    # Ensure used_tools is always a JSON array (list of names)
    try:
        used_tools = list(used_tools)
    except Exception:
        used_tools = []
    resp: AgentRespTyped = {
        "content": content,
        "used_model": backend_name,
        "used_tools": used_tools,
        "cost": cost_info,
        "timings": {},
        "metadata": {},
    }
    if screenshot_path:
        resp["screenshot"] = screenshot_path
    # attach collected diagnostic metadata
    try:
        if meta_extra:
            md = resp.get("metadata") or {}
            if isinstance(md, dict):
                md.update(meta_extra)
                resp["metadata"] = md
    except Exception:
        pass
    # attach diagnostic metadata (tool error, dependency hints) if present
    try:
        if meta_extra:
            md = resp.get("metadata")
            if not isinstance(md, dict):
                md = {}
            md.update(meta_extra)
            resp["metadata"] = md
    except Exception:
        pass

    # Step 7: Best-effort audit insert (soft-fail)
    try:
        # Collapse user prompt
        prompt_parts: List[str] = []
        for m in agent_request["messages"]:
            if m.get("role") == "user" and m.get("content"):
                prompt_parts.append(str(m.get("content")))
        user_prompt = "\n".join(prompt_parts)

        insert_agent_request(
            backend=backend_name,
            tokens_in=cost_info.get("tokens_in"),
            tokens_out=cost_info.get("tokens_out"),
            approx_cost=cost_info.get("approx_cost"),
            user_prompt=user_prompt,
            assistant_content=content or "",
        )
    except Exception as _e:
        # Do not block request on audit failure
        logger.warning("agent audit insert failed: %s", _e)
    return resp

@app.get("/")
async def root():
    return PlainTextResponse("ChatStack: see /docs")


@app.get("/agent/history")
async def agent_history(limit: int = 10):
    """Return last `limit` audit rows from agent_requests (ordered by id desc)."""
    try:
        lim = int(limit)
    except Exception:
        lim = 10
    if lim <= 0:
        lim = 10
    # Hard cap to avoid accidental huge pulls
    if lim > 200:
        lim = 200
    rows = list_agent_requests(lim)
    return rows

@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    detail = {"detail": "internal_error"}
    # Include basic exception info
    try:
        detail["error_type"] = exc.__class__.__name__
        msg = str(exc)
        if msg:
            detail["error_message"] = msg[:500]
    except Exception:
        pass
    # Best-effort include upstream error info (useful for debugging only)
    try:
        response = getattr(exc, "response", None)
        if response is not None:
            # httpx errors often have .response with .status_code and .text
            status_code = getattr(response, "status_code", None)
            text = None
            try:
                text = getattr(response, "text", None)
            except Exception:
                text = None
            if status_code is not None:
                detail["upstream_status"] = str(status_code)
            if text:
                # Truncate to avoid flooding logs/clients
                detail["upstream_body"] = text[:2000]
    except Exception:
        pass
    return JSONResponse(status_code=500, content=detail)
