# main.py - FINAL CORRECTED CODE

from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager
from typing import Any, Dict, List
import importlib.util
import os
import sys
from pathlib import Path
import uvicorn
import inspect
import json
import traceback

# ADDED: Centralized state and E2B imports
from routes.state_manager import get_sandbox_state
try:
    from e2b_code_interpreter import Sandbox as E2BSandbox
except Exception:
    E2BSandbox = None

# --- Project Paths (No changes) ---
ROOT = Path(__file__).parent.resolve()
ROUTES_DIR = ROOT / "routes"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- Module Importer (No changes) ---
def import_module_from_path(module_name: str, file_path: Path):
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot import {module_name} from {file_path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"[main] Error importing {module_name}: {e}")
        traceback.print_exc()
        return None

# --- Load All Route Modules (No changes) ---
MODULES: Dict[str, Any] = {}
def _load_all():
    # Ensure this list contains all your route files
    module_specs = [
        ("apply_ai_code_stream", "apply_ai_code_stream.py"),
        ("create_ai_sandbox", "create_ai_sandbox.py"),
        ("conversation_state", "conversation_state.py"),
        ("generate_ai_stream", "generate_ai_stream.py"),
        ("get_sandbox_files", "get_sandbox_files.py"),
        ("install_packages", "install_packages.py"),
        ("restart_vite", "restart_vite.py"),
        ("scrape_screenshot", "scrape_screenshot.py"),
        ("scrape_url_enhanced", "scrape_url_enhanced.py"),
        ("sandbox_status", "sandbox_status.py"),
        ("kill_sandbox", "kill_sandbox.py"),
        ("check_vite_errors", "check_vite_errors.py"),
        ("clear_vite_errors_cache", "clear_vite_errors_cache.py"),
        ("monitor_vite_logs", "monitor_vite_logs.py"),
        ("report_vite_error", "report_vite_error.py"),
        ("detect_and_install_packages", "detect_and_install_packages.py"),
        ("create_zip", "create_zip.py"),
        ("run_command", "run_command.py"),
        ("sandbox_logs", "sandbox_logs.py"),
        ("analyze_edit_intent", "analyze_edit_intent.py"),
    ]
    for alias, fname in module_specs:
        module_path = ROUTES_DIR / fname
        if module_path.exists():
            module = import_module_from_path(alias, module_path)
            if module:
                MODULES[alias] = module
                print(f"[main] Successfully loaded {alias}")
        else:
            print(f"[main] Module file not found: {fname}")

_load_all()

# REMOVED: The old state management functions (sync_globals, recover_sandbox_state) are gone.

async def maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value

# --- NEW: FastAPI Dependency for Sandbox Management ---
async def get_active_sandbox() -> Any:
    """
    FastAPI dependency to get a connection to the currently active sandbox.
    It reads the ID from our central state file and connects.
    This will be used by any endpoint that needs to interact with the sandbox.
    """
    if not E2BSandbox:
        raise HTTPException(status_code=500, detail="E2B SDK is not installed on the server.")

    state = get_sandbox_state()
    if not state or not state.get("sandboxId"):
        raise HTTPException(status_code=404, detail="No active sandbox. Please create one first via POST /api/create-ai-sandbox.")

    sandbox_id = state["sandboxId"]
    try:
        api_key = os.getenv("E2B_API_KEY")
        sandbox =E2BSandbox.connect(sandbox_id, api_key=api_key)
        return sandbox
    except Exception as e:
        print(f"[dependency] Failed to connect to sandbox {sandbox_id}: {e}")
        raise HTTPException(status_code=503, detail=f"Could not connect to the active sandbox. It may have timed out.")

# --- FastAPI Lifespan & App Initialization (Simplified) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Backend starting...")
    yield
    print("🛑 Backend shutting down...")

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Utility Functions (No changes) ---
def create_error_response(message: str, status: int = 500) -> JSONResponse:
    print(f"Error Response: {message}")
    return JSONResponse(content={"success": False, "error": message}, status_code=status)

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return super().default(obj)

class CustomJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content, ensure_ascii=False, allow_nan=False, indent=None,
            separators=(",", ":"), cls=CustomJSONEncoder
        ).encode("utf-8")

# --- API Endpoints ---

@app.get("/health")
async def health():
    return {"status": "healthy", "modules_loaded": list(MODULES.keys())}

# --- Sandbox Management ---
@app.post("/api/create-ai-sandbox")
async def api_create_ai_sandbox():
    mod = MODULES.get("create_ai_sandbox")
    if not mod: return create_error_response("Create sandbox module not loaded")
    result = await maybe_await(mod.POST())
    return CustomJSONResponse(result)

@app.post("/api/kill-sandbox")
async def api_kill_sandbox():
    mod = MODULES.get("kill_sandbox")
    if not mod: return create_error_response("Kill sandbox module not loaded")
    result = await maybe_await(mod.POST())
    return CustomJSONResponse(result)

@app.get("/api/sandbox-status")
async def api_sandbox_status():
    state = get_sandbox_state()
    if state:
        return CustomJSONResponse({"success": True, "active": True, "healthy": True, "sandboxData": state, "message": "Sandbox is active."})
    else:
        return CustomJSONResponse({"success": True, "active": False, "healthy": False, "sandboxData": None, "message": "No active sandbox."})

# --- Web Scraping ---
@app.post("/api/scrape-screenshot")
async def api_scrape_screenshot(request: Request, sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("scrape_screenshot")
    if not mod: return create_error_response("Scrape Screenshot module not loaded")
    mod.active_sandbox = sandbox
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)

@app.post("/api/scrape-url-enhanced")
async def api_scrape_url_enhanced(request: Request, sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("scrape_url_enhanced")
    if not mod: return create_error_response("Scrape URL module not loaded")
    mod.active_sandbox = sandbox
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)

# --- Code Generation and Application ---
@app.post("/api/generate-ai-code-stream")
async def api_generate_ai_code_stream(request: Request):
    mod = MODULES.get("generate_ai_stream")
    if not mod: return create_error_response("Generator module not loaded")
    body = await request.json()
    async def stream_generator():
        stream = mod.stream_generate_code(
            prompt=body.get("prompt", ""),
            model=body.get("model", "openai/gpt-4o-mini"),
            context=body.get("context", {}),
            is_edit=body.get("isEdit", False)
        )
        async for chunk in stream:
            yield f"data: {json.dumps(chunk)}\n\n"
    return StreamingResponse(stream_generator(), media_type="text/event-stream")

@app.post("/api/apply-ai-code-stream")
async def api_apply_ai_code_stream(request: Request, sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("apply_ai_code_stream")
    if not mod: return create_error_response("Apply code module not loaded")
    mod.active_sandbox = sandbox
    body = await request.json()
    response = await maybe_await(mod.POST(body))
    return response if hasattr(response, 'headers') else CustomJSONResponse(response)

# --- Conversation Management ---
@app.api_route("/api/conversation-state", methods=["GET", "POST", "DELETE"])
async def api_conversation_state(request: Request):
    mod = MODULES.get("conversation_state")
    if not mod: return create_error_response("Conversation state module not loaded")
    if request.method == "GET":
        result = await maybe_await(mod.GET())
    elif request.method == "DELETE":
        result = await maybe_await(mod.DELETE())
    else:
        body = await request.json()
        result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(content=result)

# --- Additional Sandbox Interaction Endpoints ---
@app.post("/api/restart-vite")
async def api_restart_vite(sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("restart_vite")
    if not mod: return create_error_response("Restart Vite module not loaded")
    mod.active_sandbox = sandbox
    result = await maybe_await(mod.POST())
    return CustomJSONResponse(result)

@app.get("/api/get-sandbox-files")
async def api_get_sandbox_files(sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("get_sandbox_files")
    if not mod: return create_error_response("Get sandbox files module not loaded")
    mod.active_sandbox = sandbox
    result = await maybe_await(mod.GET())
    return CustomJSONResponse(result)

@app.get("/api/check-vite-errors")
async def api_check_vite_errors(sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("check_vite_errors")
    if not mod: return create_error_response("Check Vite errors module not loaded")
    mod.active_sandbox = sandbox
    result = await maybe_await(mod.GET())
    return CustomJSONResponse(result)

@app.post("/api/clear-vite-errors-cache")
async def api_clear_vite_errors_cache(sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("clear_vite_errors_cache")
    if not mod: return create_error_response("Clear Vite errors cache module not loaded")
    mod.active_sandbox = sandbox
    result = await maybe_await(mod.POST())
    return CustomJSONResponse(result)

@app.get("/api/monitor-vite-logs")
async def api_monitor_vite_logs(sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("monitor_vite_logs")
    if not mod: return create_error_response("Monitor Vite logs module not loaded")
    mod.active_sandbox = sandbox
    result = await maybe_await(mod.GET())
    return result # Assumes it might be a StreamingResponse

@app.post("/api/report-vite-error")
async def api_report_vite_error(request: Request, sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("report_vite_error")
    if not mod: return create_error_response("Report Vite error module not loaded")
    mod.active_sandbox = sandbox
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)

@app.post("/api/install-packages")
async def api_install_packages(request: Request, sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("install_packages")
    if not mod: return create_error_response("Install packages module not loaded")
    mod.active_sandbox = sandbox
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return result # Could be StreamingResponse or JSON

@app.post("/api/detect-and-install-packages")
async def api_detect_and_install_packages(request: Request, sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("detect_and_install_packages")
    if not mod: return create_error_response("Detect and install packages module not loaded")
    mod.active_sandbox = sandbox
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return result # Could be StreamingResponse or JSON

@app.post("/api/create-zip")
async def api_create_zip(sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("create_zip")
    if not mod: return create_error_response("Create zip module not loaded")
    mod.active_sandbox = sandbox
    result = await maybe_await(mod.POST())
    return CustomJSONResponse(result)

@app.post("/api/run-command")
async def api_run_command(request: Request, sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("run_command")
    if not mod: return create_error_response("Run command module not loaded")
    mod.active_sandbox = sandbox
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)

@app.get("/api/sandbox-logs")
async def api_sandbox_logs(sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("sandbox_logs")
    if not mod: return create_error_response("Sandbox logs module not loaded")
    mod.active_sandbox = sandbox
    result = await maybe_await(mod.GET())
    return CustomJSONResponse(result)

@app.post("/api/analyze-edit-intent")
async def api_analyze_edit_intent(request: Request, sandbox: Any = Depends(get_active_sandbox)):
    mod = MODULES.get("analyze_edit_intent")
    if not mod: return create_error_response("Analyze edit intent module not loaded")
    mod.active_sandbox = sandbox
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)


# --- Main Entrypoint ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"🚀 Backend ready and running on http://localhost:{port}")
    # For production on Render, reload should be False
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)