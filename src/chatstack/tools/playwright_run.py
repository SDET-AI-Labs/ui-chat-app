from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, Callable, Awaitable, cast
import inspect
import uuid
from pathlib import Path

# We will import playwright in a controlled scope only when running

SAFE_IMPORT_PATTERN = re.compile(r"\b(import|from)\b", re.IGNORECASE)
MAX_SCRIPT_LENGTH = 8000  # characters
TIMEOUT_SECONDS = 30
DIFF_THRESHOLD_PERCENT = 2.0  # Allowed pixel difference percentage for visual baseline comparisons


def _validate_script(script: str) -> None:
    if not isinstance(script, str) or not script.strip():
        raise ValueError("script must be a non-empty string")
    if len(script) > MAX_SCRIPT_LENGTH:
        raise ValueError("script too long")
    # Disallow any import statements in the provided script
    if SAFE_IMPORT_PATTERN.search(script):
        raise ValueError("imports are not allowed in playwright_run script")


def _build_runner(script: str) -> Callable[[Any, Any], Awaitable[Any]]:
    # Build a sandboxed runner function. Provide only the allowed names.
    # We will only expose 'page' and minimal helpers; no builtins or globals are passed in.
    # Indent user script so it safely lives inside the async function body
    lines = script.splitlines()
    indented = "\n".join(("    " + ln) if ln.strip() != "" else "" for ln in lines)
    code = (
        "async def __sandbox_main__(page, request):\n"
        "    # User script begins\n"
        f"{indented}\n"
        "    # User script ends\n"
        "    return None\n"
    )
    local_ns: Dict[str, Any] = {}
    # No globals, very restricted locals; exec only defines __sandbox_main__
    exec(  # noqa: S102 (we restrict and validate above)
        code,
        {"__builtins__": {}},
        local_ns,
    )
    fn = local_ns.get("__sandbox_main__")
    if not callable(fn) or not inspect.iscoroutinefunction(fn):
        raise RuntimeError("failed to build sandbox runner")
    return cast(Callable[[Any, Any], Awaitable[Any]], fn)


async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Run a simple Playwright script in headless mode.

    Args:
    args: {"script": str, "screenshot"?: bool, "baseline"?: str, "api"?: bool, "insecure"?: bool}
    Returns:
        {"result": str, "error"?: str}
    """
    try:
        script_any = args.get("script") if isinstance(args, dict) else None
        if not isinstance(script_any, str):
            raise ValueError("script must be a string")
        script = script_any
        _validate_script(script)

        baseline_name: str | None = None
        api_mode = bool(args.get("api")) if isinstance(args, dict) else False
        if isinstance(args, dict):
            _b = args.get("baseline")
            if isinstance(_b, str):
                _bs = _b.strip()
                if _bs:
                    baseline_name = _bs
        screenshot_flag = (bool(args.get("screenshot")) if isinstance(args, dict) else False) or (baseline_name is not None)
        insecure_flag = bool(args.get("insecure")) if isinstance(args, dict) else False

        # Import here to avoid exposing import in user script scope
        from playwright.async_api import async_playwright  # type: ignore

        async def _execute() -> Dict[str, Any]:
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    context = await browser.new_context(ignore_https_errors=insecure_flag)
                    page = await context.new_page()
                    # API request context if requested
                    api_request = await p.request.new_context(ignore_https_errors=insecure_flag) if api_mode else None
                    # Build sandboxed function and run it
                    fn = _build_runner(script)
                    try:
                        result = await fn(page, api_request)
                    except TypeError:
                        # Backward safety: if signature mismatch occurs, call with only page
                        result = await fn(page, None)
                    # After successful script run, optionally take a screenshot
                    screenshot_path_rel: str | None = None
                    screenshot_path_abs: Path | None = None
                    if screenshot_flag:
                        # Determine project root (prefer folder containing 'data')
                        start = Path(__file__).resolve()
                        root = start
                        data_root = None
                        for anc in [start, *start.parents]:
                            if (anc / "data").is_dir():
                                data_root = anc
                                break
                            if (anc / "src").is_dir():
                                root = anc
                        base = data_root or root
                        shots_dir = base / "data" / "screenshots"
                        shots_dir.mkdir(parents=True, exist_ok=True)
                        fname = f"{uuid.uuid4().hex}.png"
                        shot_abs = shots_dir / fname
                        await page.screenshot(path=str(shot_abs))
                        screenshot_path_abs = shot_abs
                        # Build relative path from project root
                        screenshot_path_rel = f"./data/screenshots/{fname}"
                        # Baseline comparison logic (only if baseline_name provided)
                        if baseline_name and screenshot_path_abs is not None:
                            baseline_dir = (data_root or root) / "data" / "baseline"
                            baseline_dir.mkdir(parents=True, exist_ok=True)
                            baseline_abs = baseline_dir / f"{baseline_name}.png"
                            baseline_rel = f"./data/baseline/{baseline_name}.png"
                            if not baseline_abs.exists():
                                # First time: create baseline from current screenshot
                                try:
                                    import shutil
                                    shutil.copyfile(str(screenshot_path_abs), str(baseline_abs))
                                    await context.close()
                                    await browser.close()
                                    return {
                                        "result": "baseline_created",
                                        "screenshot": screenshot_path_rel,
                                        "baseline": baseline_rel,
                                    }
                                except Exception as e:  # noqa: BLE001
                                    await context.close()
                                    await browser.close()
                                    return {"result": "error", "error": f"baseline create failed: {e}"}
                            else:
                                # Compare images
                                try:
                                    try:
                                        from PIL import Image  # type: ignore
                                    except Exception:
                                        await context.close()
                                        await browser.close()
                                        return {"result": "error", "error": "Pillow not installed (pip install Pillow)", "dependency": "Pillow", "install_hint": "pip install Pillow"}
                                    img_new = Image.open(str(screenshot_path_abs)).convert("RGB")
                                    img_base = Image.open(str(baseline_abs)).convert("RGB")
                                    if img_new.size != img_base.size:
                                        # Size mismatch -> 100% diff
                                        diff_percent = 100.0
                                    else:
                                        # Pixel-by-pixel diff
                                        new_pixels = img_new.load()
                                        base_pixels = img_base.load()
                                        if new_pixels is None or base_pixels is None:
                                            diff_percent = 100.0
                                        else:
                                            w, h = img_new.size
                                            diff_count = 0
                                            for y in range(h):
                                                for x in range(w):
                                                    if new_pixels[x, y] != base_pixels[x, y]:
                                                        diff_count += 1
                                            total = w * h
                                            diff_percent = (diff_count / total) * 100.0 if total else 0.0
                                    passed = diff_percent <= DIFF_THRESHOLD_PERCENT
                                    await context.close()
                                    await browser.close()
                                    return {
                                        "result": "pass" if passed else "fail",
                                        "diff_percent": round(diff_percent, 4),
                                        "screenshot": screenshot_path_rel,
                                        "baseline": baseline_rel,
                                    }
                                except Exception as e:  # noqa: BLE001
                                    await context.close()
                                    await browser.close()
                                    return {"result": "error", "error": f"baseline compare failed: {e}"}
                    # Cleanup API request context first
                    try:
                        if api_request is not None:
                            await api_request.dispose()
                    except Exception:
                        pass
                    await context.close()
                    await browser.close()
                # Normalize result to string
                if result is None:
                    out: Dict[str, Any] = {"result": "ok"}
                else:
                    out = {"result": str(result)}
                if screenshot_flag:
                    out["screenshot"] = screenshot_path_rel
                return out
            except Exception as e:  # noqa: BLE001
                return {"result": "error", "error": str(e)}

        return await asyncio.wait_for(_execute(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return {"result": "error", "error": "timeout"}
    except Exception as e:  # noqa: BLE001
        return {"result": "error", "error": str(e)}
