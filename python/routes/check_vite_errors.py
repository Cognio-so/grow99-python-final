# check_vite_errors.py — Final corrected version
from typing import Any, Dict, List, Optional
import re

# This global variable is set by other modules and shared across the app
active_sandbox: Optional[Any] = None

# Bring in a self-contained copy of the necessary helpers
import inspect
async def _run_in_sandbox(sb: Any, code: str) -> Any:
    exec_method = getattr(sb, "run_code", None) or getattr(sb, "run", None)
    if not exec_method: return {"output": ""}
    result = exec_method(code)
    if inspect.isawaitable(result): result = await result
    if hasattr(result, 'wait'): result.wait()
    return result
def _extract_output_safe(result: Any) -> str:
    if hasattr(result, "logs") and hasattr(result.logs, "stdout"): return "".join(map(str, result.logs.stdout))
    return getattr(result, "output", "") or ""

async def GET() -> Dict[str, Any]:
    """Checks the Vite server logs for compilation errors after an edit."""
    if active_sandbox is None: return {"success": False, "error": "No active sandbox"}

    check_command = "tail -n 30 /tmp/vite_stderr.log"
    result = await _run_in_sandbox(active_sandbox, check_command)
    log_output = _extract_output_safe(result)
    
    error_patterns = ["error", "failed to compile", "uncaught", "unexpected token", "is not defined", "cannot read properties", "syntaxerror"]
    found_errors: List[str] = []
    clean_log = re.sub(r'\x1b\[[0-9;]*m', '', log_output)

    for line in clean_log.splitlines():
        if "eaddrinuse" in line.lower() or "hmr" in line.lower(): continue
        if any(p in line.lower() for p in error_patterns):
            found_errors.append(line.strip())
            
    if found_errors:
        return {"hasErrors": True, "errors": found_errors, "message": "Vite server reported errors."}
    else:
        return {"hasErrors": False, "errors": [], "message": "Vite server is running without errors."}