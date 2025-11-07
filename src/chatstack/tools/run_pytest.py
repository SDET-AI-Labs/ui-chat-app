from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Dict, Any, List
import subprocess


def _find_project_root(start: Path) -> Path:
    """Find the project root by locating the parent of 'src' folder.
    Fallback to start if not found.
    """
    p = start.resolve()
    for ancestor in [p, *p.parents]:
        if (ancestor / "src").is_dir():
            return ancestor
    return p


def _build_pytest_command(args: Dict[str, Any]) -> List[str]:
    cmd = [sys.executable, "-m", "pytest", "-q", "--disable-warnings", "--maxfail=1"]
    # Optional path(s)
    paths = args.get("paths") if isinstance(args, dict) else None
    if isinstance(paths, str) and paths.strip():
        cmd.append(paths.strip())
    elif isinstance(paths, list):
        for p in paths:
            if isinstance(p, str) and p.strip():
                cmd.append(p.strip())
    return cmd


def _parse_summary(output: str) -> Dict[str, Any]:
    """Extract pytest summary numbers and simple no-tests detection.

    Returns keys: passed, failed, skipped, collected (optional), no_tests (bool)
    """
    passed = failed = skipped = 0
    collected: int | None = None
    no_tests = False
    m = re.search(r"(\d+)\s+passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", output)
    if m:
        failed = int(m.group(1))
    m = re.search(r"(\d+)\s+skipped", output)
    if m:
        skipped = int(m.group(1))
    # Detect 'no tests ran' pattern
    if re.search(r"no tests ran", output, re.IGNORECASE):
        no_tests = True
        collected = 0
    # Also try to parse collected items if present
    m = re.search(r"collected\s+(\d+)\s+items?", output)
    if m:
        collected = int(m.group(1))

    result: Dict[str, Any] = {"passed": passed, "failed": failed, "skipped": skipped}
    if collected is not None:
        result["collected"] = collected
    if no_tests:
        result["no_tests"] = True
    return result


async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Run pytest (non-destructive) and return a summary.

    Args:
        args: {"paths": Optional[str|List[str]]}
    Returns:
        {"passed": int, "failed": int, "skipped": int, "exit_code": int}
    """
    def _exec() -> Dict[str, Any]:
        project_root = _find_project_root(Path(__file__).resolve())
        cmd = _build_pytest_command(args)
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False,
            )
        except FileNotFoundError:
            # pytest not installed or python missing
            return {"passed": 0, "failed": 0, "skipped": 0, "exit_code": 127}

        summary = _parse_summary(proc.stdout or "")
        summary["exit_code"] = int(proc.returncode)
        # Do not include full stdout to avoid spam; keep response minimal per spec.
        return summary

    return await asyncio.to_thread(_exec)
