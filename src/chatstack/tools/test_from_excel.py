from __future__ import annotations

from typing import Any, Dict, List

from . import get_tool


async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Orchestrator: read rows from Excel, visit each URL with Playwright, compare title.

    Args:
        args: {"path": "./data/testcases.xlsx", "sheet": "Sheet1"}
    Returns:
        {"results": [{"url": str, "actual_title": str | None, "expected_title": str | None, "status": "PASS"|"FAIL"}]}
    """
    path = args.get("path") if isinstance(args, dict) else None
    sheet = args.get("sheet") if isinstance(args, dict) else None
    if not isinstance(path, str) or not path:
        return {"result": "error", "error": "Missing or invalid 'path'"}
    if not isinstance(sheet, str) or not sheet:
        return {"result": "error", "error": "Missing or invalid 'sheet'"}

    # 1) Read excel rows
    excel_tool = get_tool("excel_read")
    excel_out = await excel_tool({"path": path, "sheet": sheet})
    if not isinstance(excel_out, dict) or "result" not in excel_out:
        return {"result": "error", "error": "excel_read returned unexpected shape"}
    if excel_out.get("result") == "error":
        return {"result": "error", "error": str(excel_out.get("error"))}

    rows: List[Dict[str, Any]] = list(excel_out.get("result") or [])
    results: List[Dict[str, Any]] = []

    # 2) For each row: navigate and capture title
    pw = get_tool("playwright_run")
    for r in rows:
        url = None
        expected_title = None
        try:
            url = str(r.get("url")) if r.get("url") is not None else None
            expected_title = str(r.get("expected_title")) if r.get("expected_title") is not None else None
        except Exception:
            pass
        if not url:
            results.append({
                "url": url,
                "actual_title": None,
                "expected_title": expected_title,
                "status": "FAIL"
            })
            continue

        script = (
            "title = await page.goto('" + url.replace("'", "%27") + "');\n"
            "await page.wait_for_load_state('load');\n"
            "return await page.title()\n"
        )
        try:
            out = await pw({"script": script, "screenshot": False})
            # playwright_run returns {"result": <value>} or {"result":"error", "error":...}
            if isinstance(out, dict) and out.get("result") != "error":
                actual = out.get("result")
                if not isinstance(actual, str):
                    actual = str(actual) if actual is not None else None
            else:
                actual = None
        except Exception as e:
            actual = None

        status = "PASS" if (isinstance(expected_title, str) and isinstance(actual, str) and actual.strip() == expected_title.strip()) else "FAIL"
        results.append({
            "url": url,
            "actual_title": actual,
            "expected_title": expected_title,
            "status": status,
        })

    return {"results": results}
