# shared_state.py — central, importable state for the sandbox

from typing import Any, Dict, Optional, Tuple

active_sandbox: Optional[Any] = None
sandbox_data: Optional[Dict[str, Any]] = None

def set_sandbox(sandbox: Any, data: Dict[str, Any]) -> None:
    global active_sandbox, sandbox_data
    active_sandbox = sandbox
    sandbox_data = data or {}

def get_sandbox() -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
    return active_sandbox, sandbox_data