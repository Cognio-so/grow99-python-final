# report_vite_error.py (Enhanced with detailed error parsing)

from typing import TypedDict, Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from langchain.schema.runnable import RunnableLambda
import re
from datetime import datetime

# This global list will store the last 50 processed errors in memory.
vite_errors: List[Dict[str, Any]] = []

class GraphState(TypedDict, total=False):
    payload: Dict[str, Any]
    response: Dict[str, Any]

def _process_error_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processes a raw error message to extract detailed, actionable information.
    """
    try:
        raw_error_msg = payload.get("error")
        if not raw_error_msg:
            return {"success": False, "error": "Field 'error' is required"}

        # --- Enhanced Error Parsing Logic ---

        # Define patterns for common Vite/JS errors. Order matters.
        error_patterns = [
            {
                "type": "import-error",
                "regex": r"Failed to resolve import ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]"
            },
            {
                "type": "syntax-error",
                "regex": r"(SyntaxError|Unexpected token|Unterminated string constant)\:? (.+?) \(([0-9]+)\:([0-9]+)\)"
            },
            {
                "type": "reference-error",
                "regex": r"ReferenceError\: (.+?) is not defined"
            },
            {
                "type": "type-error",
                "regex": r"TypeError\: Cannot read properties of undefined \(reading '(.+?)'\)"
            }
        ]
        
        error_obj: Dict[str, Any] = {
            "type": "generic-runtime-error",
            "message": raw_error_msg,
            "file": payload.get("file") or "unknown",
            "lineNumber": None,
            "columnNumber": None,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        # Find the first matching pattern and update the error object
        for pattern in error_patterns:
            match = re.search(pattern["regex"], raw_error_msg, re.IGNORECASE)
            if match:
                error_obj["type"] = pattern["type"]
                if pattern["type"] == "import-error":
                    error_obj["details"] = f"Could not import '{match.group(1)}'"
                    error_obj["file"] = match.group(2)
                elif pattern["type"] == "syntax-error":
                    error_obj["message"] = f"{match.group(1)}: {match.group(2)}"
                    error_obj["lineNumber"] = int(match.group(3))
                    error_obj["columnNumber"] = int(match.group(4))
                elif pattern["type"] == "reference-error":
                    error_obj["details"] = f"Variable '{match.group(1)}' was used before it was defined."
                elif pattern["type"] == "type-error":
                     error_obj["details"] = f"Attempted to access a property ('{match.group(1)}') on an undefined object."
                break
        
        # Generic fallback to find file and line number if no specific pattern matched
        if error_obj["lineNumber"] is None:
            # Example patterns: "at /path/to/file.jsx:12:5" or "in /path/to/file.js (12:5)"
            line_match = re.search(r"((?:[a-zA-Z]\:)?(?:/[\w\.-]+)+[\w\.-]+)\:([0-9]+)\:([0-9]+)", raw_error_msg)
            if line_match:
                error_obj["file"] = line_match.group(1)
                error_obj["lineNumber"] = int(line_match.group(2))
                error_obj["columnNumber"] = int(line_match.group(3))

        # --- End of Enhanced Parsing Logic ---
        
        vite_errors.append(error_obj)
        # Keep the list trimmed to the last 50 errors
        if len(vite_errors) > 50:
            del vite_errors[:-50]
            
        print(f"[report-vite-error] Processed Error: {error_obj}")
        return {"success": True, "message": "Error reported successfully", "error": error_obj}

    except Exception as e:
        print(f"[report-vite-error] Internal Error: {e}")
        return {"success": False, "error": str(e)}


# The LangGraph setup remains the same, it just uses the new processing function
_processor = RunnableLambda(_process_error_report)

def _node(state: GraphState) -> GraphState:
    payload = state.get("payload", {})
    resp = _processor.invoke(payload)
    return {"response": resp}

_sg = StateGraph(GraphState)
_sg.add_node("process", _node)
_sg.set_entry_point("process")
_sg.add_edge("process", END)
_graph = _sg.compile()

def POST(body: Dict[str, Any]) -> Dict[str, Any]:
    result = _graph.invoke({"payload": body})
    return result.get("response", {})