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
from routes.database import init_database, close_connection
import atexit
# ADDED: Centralized state and E2B imports
from routes.state_manager import get_sandbox_state
from routes.create_ai_sandbox import _create_and_setup_sandbox
from routes.database import get_sandbox_state
# ADD this to handle potential E2B SDK differences
try:
    from e2b_code_interpreter import Sandbox as E2BSandbox
except Exception:
    from e2b import Sandbox as E2BSandbox

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
# Add this to your main.py for automatic session cleanup

import asyncio
import time
from datetime import datetime, timedelta

class SessionManager:
    def __init__(self):
        self.session_timeout = 30 * 60  # 30 minutes
        self.cleanup_interval = 5 * 60   # Check every 5 minutes
        self.running = False
        
    async def start_cleanup_task(self):
        """Start background task to clean up inactive sessions"""
        self.running = True
        print("[SessionManager] Starting automatic cleanup task...")
        
        while self.running:
            try:
                await self.cleanup_inactive_sessions()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                print(f"[SessionManager] Cleanup error: {e}")
                await asyncio.sleep(self.cleanup_interval)
    
    async def cleanup_inactive_sessions(self):
        """Clean up sessions that have been inactive too long"""
        from routes.database import get_sandbox_state, set_sandbox_state
        
        try:
            state = get_sandbox_state()
            if not state:
                return
            
            # Check if session is too old
            current_time = int(time.time() * 1000)
            last_updated = state.get('updatedAt', 0)
            
            if current_time - last_updated > (self.session_timeout * 1000):
                print(f"[SessionManager] Cleaning up inactive session (idle for {(current_time - last_updated) // 1000}s)")
                
                # Kill the sandbox
                kill_module = None
                try:
                    import sys
                    main_module = sys.modules.get("main")
                    if main_module and hasattr(main_module, "MODULES"):
                        kill_module = main_module.MODULES.get("kill_sandbox")
                except:
                    pass
                
                if kill_module:
                    try:
                        result = await kill_module.POST()
                        print(f"[SessionManager] Cleanup result: {result.get('message', 'Unknown')}")
                    except Exception as e:
                        print(f"[SessionManager] Kill sandbox error: {e}")
                        # Emergency cleanup
                        set_sandbox_state(None)
                
        except Exception as e:
            print(f"[SessionManager] Session cleanup error: {e}")
    
    def stop(self):
        """Stop the cleanup task"""
        self.running = False
        print("[SessionManager] Stopping cleanup task...")

# Global session manager
session_manager = SessionManager()
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
# In main.py, REPLACE your current get_active_sandbox function with this one.

async def get_active_sandbox() -> Any:
    """
    FastAPI dependency with automatic sandbox recreation on failure.
    CORRECTED to use .connect() for SDK compatibility.
    """
    if not E2BSandbox:
        raise HTTPException(status_code=500, detail="E2B SDK is not installed on the server.")

    state = get_sandbox_state()
    
    # If a sandbox ID exists, try to connect to it.
    if state and state.get("sandboxId"):
        sandbox_id = state["sandboxId"]
        try:
            print(f"[dependency] Attempting to connect to existing sandbox: {sandbox_id}")
            api_key = os.getenv("E2B_API_KEY")
            print(f"snbox")
            sandbox = E2BSandbox.connect(sandbox_id, api_key=api_key) 
            print(f"[dependency] ✅ Successfully connected to sandbox {sandbox_id}")
            return sandbox
        except Exception as e:
            print(f"[dependency] ⚠️ Sandbox {sandbox_id} connection failed: {e}. It has likely expired.")
            print("[dependency] 🚀 Triggering automatic sandbox recreation...")
            # FALLTHROUGH to recreation logic below
    
    # If there was no state OR the connection failed, create a new sandbox.
    try:
        creation_result = await _create_and_setup_sandbox()
        if not creation_result.get("success"):
            # Use the error message from the creation function if available
            error_detail = creation_result.get("error", "Failed to automatically recreate sandbox.")
            raise HTTPException(status_code=500, detail=error_detail)
        
        new_sandbox_id = creation_result["sandboxId"]
        print(f"[dependency] 🔄 New sandbox {new_sandbox_id} created. Connecting to finalize...")
        api_key = os.getenv("E2B_API_KEY")
        # --- FIX 2: Use .connect() here as well ---
        new_sandbox = E2BSandbox.connect(new_sandbox_id, api_key=api_key)
        print(f"[dependency] ✅ Connection to new sandbox successful. Proceeding with request.")
        return new_sandbox
        
    except Exception as e:
        print(f"[dependency] ❌ CRITICAL: Automatic recreation failed. Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Sandbox expired and automatic recreation failed: {e}")

# --- FastAPI Lifespan & App Initialization (Simplified) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("ðŸš€ Backend starting...")
    init_database()
    cleanup_task = asyncio.create_task(session_manager.start_cleanup_task())
    yield
    print("ðŸ›‘ Backend shutting down...")
    session_manager.stop()
    cleanup_task.cancel()

    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    # close_connection()
    close_connection()
atexit.register(close_connection)

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
async def api_create_ai_sandbox(request: Request):
    mod = MODULES.get("create_ai_sandbox")
    if not mod: return create_error_response("Create sandbox module not loaded")
    
    # Get client IP
    client_ip = request.client.host if hasattr(request, 'client') else 'unknown'
    
    result = await maybe_await(mod.POST())
    
    # Update state with IP tracking if successful
    if result.get('success'):
        try:
            from routes.database import get_sandbox_state, set_sandbox_state
            state = get_sandbox_state()
            if state:
                # Update with IP and session info
                import uuid
                session_id = str(uuid.uuid4())
                set_sandbox_state(state, user_ip=client_ip, session_id=session_id)
        except Exception as e:
            print(f"[create_sandbox] Error updating state with IP: {e}")
    
    return CustomJSONResponse(result)

@app.post("/api/kill-sandbox")
async def api_kill_sandbox():
    mod = MODULES.get("kill_sandbox")
    if not mod: return create_error_response("Kill sandbox module not loaded")
    result = await maybe_await(mod.POST())
    return CustomJSONResponse(result)

@app.get("/api/debug/storage")
async def debug_storage():
    from pathlib import Path
    
    storage_path = Path('/app/data')
    
    return {
        "path": str(storage_path),
        "exists": storage_path.exists(),
        "is_dir": storage_path.is_dir(),
        "writable": os.access(storage_path, os.W_OK),
        "files": list(storage_path.glob('*')) if storage_path.exists() else [],
        "db_exists": (storage_path / 'sandbox_state.db').exists()
    }

@app.get("/api/sandbox-status")
async def api_sandbox_status():
    from routes.database import get_sandbox_state, set_sandbox_state
    
    state = get_sandbox_state()
    if not state:
        return CustomJSONResponse({
            "success": True, 
            "active": False, 
            "healthy": False, 
            "sandboxData": None, 
            "message": "No active sandbox."
        })
    
    # Verify sandbox is still accessible
    try:
        if E2BSandbox:
            api_key = os.getenv("E2B_API_KEY")
            sandbox = E2BSandbox.connect(state["sandboxId"], api_key=api_key)
            # Test connection with a simple operation
            if hasattr(sandbox, 'run_code'):
                test_result = sandbox.run_code("print('test')")
            
            return CustomJSONResponse({
                "success": True, 
                "active": True, 
                "healthy": True, 
                "sandboxData": state, 
                "message": "Sandbox is active."
            })
    except Exception as e:
        print(f"[sandbox-status] Sandbox {state['sandboxId']} verification failed: {e}")
        # Clear expired sandbox state
        set_sandbox_state(None)
        return CustomJSONResponse({
            "success": True, 
            "active": False, 
            "healthy": False, 
            "sandboxData": None, 
            "message": "Sandbox has expired and was cleared."
        })
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
from fastapi import Request
import time

@app.middleware("http")
async def activity_tracking_middleware(request: Request, call_next):
    """Track user activity for session management"""
    
    # Update activity on any API call
    if request.url.path.startswith("/api/"):
        try:
            from routes.database import update_activity
            update_activity()
        except Exception as e:
            print(f"[activity_tracking] Error updating activity: {e}")
    
    response = await call_next(request)
    return response
@app.get("/api/debug/cleanup-stats")
async def debug_cleanup_stats():
    try:
        from routes.database import get_cleanup_stats
        stats = get_cleanup_stats()
        return CustomJSONResponse({
            "success": True,
            **stats
        })
    except Exception as e:
        return create_error_response(f"Failed to get cleanup stats: {str(e)}")
# --- Main Entrypoint ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"ðŸš€ Backend ready and running on http://localhost:{port}")
    # For production on Render, reload should be False
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)