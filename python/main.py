# main.py

from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException
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

# --- Project Paths ---
ROOT = Path(__file__).parent.resolve()
# This allows the script to find the /routes directory
ROUTES_DIR = ROOT / "routes"
if not ROUTES_DIR.exists():
    # A fallback for different environments if necessary
    ROUTES_DIR = Path("/mnt/data/routes")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- Module Importer ---
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

# --- Load All Route Modules ---
MODULES: Dict[str, Any] = {}
def _load_all():
    # This list should contain all your .py files from the /routes directory
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
        # Add any other modules here
        ("check_vite_errors", "check_vite_errors.py"),
        ("clear_vite_errors_cache", "clear_vite_errors_cache.py"),
        ("monitor_vite_logs", "monitor_vite_logs.py"),
        ("report_vite_error", "report_vite_error.py"),
        ("detect_and_install_packages", "detect_and_install_packages.py"),
        ("create_zip", "create_zip.py"),
        ("run_command", "run_command.py"),
        ("sandbox_logs", "sandbox_logs.py"),
        ("analyze_edit_intent", "analyze_edit_intent.py"),
        # ("debug_sandbox_urls", "debug-sandbox-urls.py"),

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

# --- Global State Synchronization - FIXED ---
SHARED_ATTRS = ("active_sandbox", "sandbox_state", "sandbox_data", "existing_files", "conversation_state")

async def sync_globals():
    try:
        # Find the primary source - module that actually has an active sandbox
        primary_source = None
        source_name = None
        
        # Check for modules with active sandbox first
        for name, module in MODULES.items():
            if module and hasattr(module, "active_sandbox"):
                sandbox = getattr(module, "active_sandbox", None)
                if sandbox is not None:
                    primary_source = module
                    source_name = name
                    print(f"[sync] Using {name} as primary source (has active_sandbox)")
                    break
        
        # Fallback: check for modules with sandbox_state that has fileCache
        if not primary_source:
            for name, module in MODULES.items():
                if module and hasattr(module, "sandbox_state"):
                    sandbox_state = getattr(module, "sandbox_state", None)
                    if sandbox_state and isinstance(sandbox_state, dict):
                        if sandbox_state.get("fileCache"):
                            primary_source = module
                            source_name = name
                            print(f"[sync] Using {name} as primary source (has fileCache)")
                            break
        
        if not primary_source:
            print("[sync] No primary source found")
            return
        
        # Get the active sandbox and related data from primary source
        active_sandbox_value = getattr(primary_source, "active_sandbox", None)
        sandbox_data_value = getattr(primary_source, "sandbox_data", None)
        existing_files_value = getattr(primary_source, "existing_files", set())
        sandbox_state_value = getattr(primary_source, "sandbox_state", None)
        
        # Sync to ALL modules that need these values
        synced_count = 0
        target_modules = [
            "create_ai_sandbox", "apply_ai_code_stream", "get_sandbox_files", 
            "sandbox_status", "restart_vite", "kill_sandbox", "sandbox_logs"
        ]
        
        for module_name in target_modules:
            module = MODULES.get(module_name)
            if module and module != primary_source:
                # Sync active_sandbox
                if hasattr(module, "active_sandbox"):
                    setattr(module, "active_sandbox", active_sandbox_value)
                    synced_count += 1
                
                # Sync sandbox_data
                if hasattr(module, "sandbox_data"):
                    setattr(module, "sandbox_data", sandbox_data_value)
                    synced_count += 1
                
                # Sync existing_files
                if hasattr(module, "existing_files"):
                    setattr(module, "existing_files", existing_files_value)
                    synced_count += 1
                
                # Sync sandbox_state
                if hasattr(module, "sandbox_state"):
                    setattr(module, "sandbox_state", sandbox_state_value)
                    synced_count += 1
        
        print(f"[sync] Synced {synced_count} attributes from {source_name} to {len(target_modules)-1} modules")
        
    except Exception as e:
        print(f"[sync] Error: {e}")
        import traceback
        traceback.print_exc()

async def recover_sandbox_state():
    """Try to recover sandbox state from persistent storage"""
    try:
        # Check if we have a saved sandbox
        if os.path.exists('/tmp/g99_sandbox.json'):
            with open('/tmp/g99_sandbox.json', 'r') as f:
                saved_data = json.load(f)
            
            sandbox_id = saved_data.get('sandboxId')
            url = saved_data.get('url')
            files = saved_data.get('files', [])
            
            if sandbox_id and saved_data.get('active'):
                print(f"[recovery] Found saved sandbox: {sandbox_id}")
                
                # Try to reconnect to existing sandbox
                try:
                    from e2b_code_interpreter import Sandbox as E2BSandbox
                    api_key = os.getenv("E2B_API_KEY")
                    
                    # Try to connect to existing sandbox
                    if hasattr(E2BSandbox, 'connect'):
                        if inspect.iscoroutinefunction(E2BSandbox.connect):
                            sandbox = await E2BSandbox.connect(sandbox_id, api_key=api_key)
                        else:
                            sandbox = E2BSandbox.connect(sandbox_id, api_key=api_key)
                    else:
                        # If connect method doesn't exist, create new one
                        if inspect.iscoroutinefunction(E2BSandbox.create):
                            sandbox = await E2BSandbox.create(api_key=api_key)
                        else:
                            sandbox = E2BSandbox.create(api_key=api_key)
                        # Get new sandbox ID
                        sandbox_id = getattr(sandbox, 'id', None) or getattr(sandbox, 'sandbox_id', None)
                    
                    # Set in create_ai_sandbox module
                    create_mod = MODULES.get("create_ai_sandbox")
                    if create_mod:
                        create_mod.active_sandbox = sandbox
                        create_mod.sandbox_data = {"sandboxId": sandbox_id, "url": url}
                        create_mod.existing_files = set(files)
                        create_mod.sandbox_state = {
                            "fileCache": {
                                "files": {},
                                "lastSync": int(time.time() * 1000),
                                "sandboxId": sandbox_id,
                            },
                            "sandbox": sandbox,
                            "sandboxData": {
                                "sandboxId": sandbox_id,
                                "url": url,
                            },
                        }
                    
                    print("[recovery] State recovered successfully!")
                    return True
                    
                except Exception as e:
                    print(f"[recovery] Failed to recover sandbox: {e}")
                    # Clear invalid state file
                    try:
                        os.remove('/tmp/g99_sandbox.json')
                    except:
                        pass
                    
    except Exception as e:
        print(f"[recovery] Recovery failed: {e}")
    
    return False

async def maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value

# --- FastAPI Lifespan & App Initialization - FIXED ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Backend starting...")
    
    # CRITICAL: Try to recover sandbox state first
    await recover_sandbox_state()
    
    # Then sync globals
    await sync_globals()
    
    yield
    print("🛑 Backend shutting down...")
    # Add sandbox cleanup logic here if needed

# Initialize sandbox status module with shared state
sandbox_status_mod = MODULES.get("sandbox_status")
if sandbox_status_mod:
    sandbox_status_mod.active_sandbox = None
    sandbox_status_mod.sandbox_state = {}
    sandbox_status_mod.sandbox_data = {}

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- Utility Functions for Responses ---
def create_error_response(message: str, status: int = 500) -> JSONResponse:
    print(f"Error Response: {message}")
    return JSONResponse(content={"success": False, "error": message}, status_code=status)

# Custom JSON encoder to handle non-serializable objects
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)

# Override default JSONResponse to use our custom encoder
class CustomJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
            cls=CustomJSONEncoder
        ).encode("utf-8")

# --- API Endpoints ---

@app.get("/health")
async def health():
    return {"status": "healthy", "modules_loaded": list(MODULES.keys())}

# ADD: Debug endpoint to check sandbox state
@app.get("/api/debug-sandbox-state")
async def debug_sandbox_state():
    await sync_globals()
    
    debug_info = {}
    for name, module in MODULES.items():
        if hasattr(module, "active_sandbox"):
            active_sandbox = getattr(module, "active_sandbox", None)
            sandbox_data = getattr(module, "sandbox_data", None)
            existing_files = getattr(module, "existing_files", set())
            
            debug_info[name] = {
                "has_active_sandbox": active_sandbox is not None,
                "sandbox_data": sandbox_data,
                "files_count": len(existing_files) if existing_files else 0,
                "files": list(existing_files) if existing_files else []
            }
    
    # Check persistent storage
    persistent_state = None
    if os.path.exists('/tmp/g99_sandbox.json'):
        try:
            with open('/tmp/g99_sandbox.json', 'r') as f:
                persistent_state = json.load(f)
        except:
            pass
    
    return {
        "modules": debug_info,
        "persistent_state": persistent_state,
        "render_env": os.environ.get("RENDER", "not_render")
    }

# --- Sandbox Management ---

@app.post("/api/create-ai-sandbox")
async def api_create_ai_sandbox():
    try:
        mod = MODULES.get("create_ai_sandbox")
        if not mod: return create_error_response("Create sandbox module not loaded")
        
        result = await maybe_await(mod.POST())
        if result.get("success"):
            await sync_globals()
            return CustomJSONResponse(result)
        else:
            return create_error_response(result.get("error", "Sandbox creation failed"), result.get("status", 500))
    except Exception as e:
        return create_error_response(f"Sandbox creation failed: {traceback.format_exc()}")

@app.get("/api/sandbox-status")
async def api_sandbox_status():
    await sync_globals()
    mod = MODULES.get("sandbox_status")
    if not mod: return create_error_response("Status module not loaded")
    
    if hasattr(mod, 'get_sandbox_status'):
        result = await maybe_await(mod.get_sandbox_status())
    elif hasattr(mod, 'GET'):
        result = await maybe_await(mod.GET())
    else:
        return create_error_response("Status module has no valid method")
    
    return CustomJSONResponse(result)

@app.post("/api/restart-vite")
async def api_restart_vite():
    await sync_globals()
    mod = MODULES.get("restart_vite")
    if not mod: return create_error_response("Restart Vite module not loaded")
    result = await maybe_await(mod.POST())
    return CustomJSONResponse(result)

# --- Web Scraping ---

@app.post("/api/scrape-screenshot")
async def api_scrape_screenshot(request: Request):
    mod = MODULES.get("scrape_screenshot")
    if not mod: return create_error_response("Scrape Screenshot module not loaded")
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)

@app.post("/api/scrape-url-enhanced")
async def api_scrape_url_enhanced(request: Request):
    mod = MODULES.get("scrape_url_enhanced")
    if not mod: return create_error_response("Scrape URL module not loaded")
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)

# --- Code Generation and Application ---

@app.post("/api/generate-ai-code-stream")
async def api_generate_ai_code_stream(request: Request):
    await sync_globals()
    mod = MODULES.get("generate_ai_stream")
    if not mod: return create_error_response("Generator module not loaded")

    body = await request.json()
    
    async def stream_generator():
        # Assumes generate_ai_stream.py has a streaming function
        if hasattr(mod, "stream_generate_code"):
            stream = mod.stream_generate_code(
                prompt=body.get("prompt", ""),
                model=body.get("model", "openai/gpt-4o-mini"),
                context=body.get("context", {}),
                is_edit=body.get("isEdit", False)
            )
            async for chunk in stream:
                yield f"data: {json.dumps(chunk)}\n\n"
        else:
            # Fallback for non-streaming generation
            result = await maybe_await(mod.generate_code(**body))
            yield f"data: {json.dumps(result)}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

# Fix for main.py - Replace the existing api_apply_ai_code_stream function

@app.post("/api/apply-ai-code-stream")
async def api_apply_ai_code_stream(request: Request):
    await sync_globals()
    mod = MODULES.get("apply_ai_code_stream")
    if not mod: return create_error_response("Apply code module not loaded")
    
    body = await request.json()
    response = await maybe_await(mod.POST(body))
    
    # Sync globals back after applying code - CRITICAL FOR RENDER
    await sync_globals()
    
    # CRITICAL FIX: Check if response is already a FastAPI response object
    # StreamingResponse, JSONResponse, etc. should be returned directly
    if hasattr(response, 'headers') and hasattr(response, 'media_type'):
        return response
    elif hasattr(response, '__class__') and 'Response' in str(response.__class__):
        return response
    else:
        # Only wrap dict/plain objects in CustomJSONResponse
        return CustomJSONResponse(response)

# --- Conversation Management ---

@app.api_route("/api/conversation-state", methods=["GET", "POST", "DELETE"])
async def api_conversation_state(request: Request):
    mod = MODULES.get("conversation_state")
    if not mod: return create_error_response("Conversation state module not loaded")

    if request.method == "GET":
        result = await maybe_await(mod.GET())
    elif request.method == "DELETE":
        result = await maybe_await(mod.DELETE())
    else: # POST
        body = await request.json()
        result = await maybe_await(mod.POST(body))
    
    return CustomJSONResponse(content=result)

# --- Additional Endpoints ---

@app.post("/api/kill-sandbox")
async def api_kill_sandbox():
    await sync_globals()
    mod = MODULES.get("kill_sandbox")
    if not mod: return create_error_response("Kill sandbox module not loaded")
    result = await maybe_await(mod.POST())
    await sync_globals()  # Sync after killing sandbox
    return CustomJSONResponse(result)

@app.get("/api/get-sandbox-files")
async def api_get_sandbox_files():
    await sync_globals()
    mod = MODULES.get("get_sandbox_files")
    if not mod: return create_error_response("Get sandbox files module not loaded")
    result = await maybe_await(mod.GET())
    return CustomJSONResponse(result)

@app.get("/api/check-vite-errors")
async def api_check_vite_errors():
    await sync_globals()
    mod = MODULES.get("check_vite_errors")
    if not mod: return create_error_response("Check Vite errors module not loaded")
    result = await maybe_await(mod.GET())
    return CustomJSONResponse(result)

@app.post("/api/clear-vite-errors-cache")
async def api_clear_vite_errors_cache():
    await sync_globals()
    mod = MODULES.get("clear_vite_errors_cache")
    if not mod: return create_error_response("Clear Vite errors cache module not loaded")
    result = await maybe_await(mod.POST())
    return CustomJSONResponse(result)

@app.get("/api/monitor-vite-logs")
async def api_monitor_vite_logs():
    await sync_globals()
    mod = MODULES.get("monitor_vite_logs")
    if not mod: return create_error_response("Monitor Vite logs module not loaded")
    result = await maybe_await(mod.GET())
    return CustomJSONResponse(result)  # StreamingResponse

@app.post("/api/report-vite-error")
async def api_report_vite_error(request: Request):
    await sync_globals()
    mod = MODULES.get("report_vite_error")
    if not mod: return create_error_response("Report Vite error module not loaded")
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)

@app.post("/api/install-packages")
async def api_install_packages(request: Request):
    await sync_globals()
    mod = MODULES.get("install_packages")
    if not mod: return create_error_response("Install packages module not loaded")
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)  # Could be StreamingResponse or JSON

@app.post("/api/detect-and-install-packages")
async def api_detect_and_install_packages(request: Request):
    await sync_globals()
    mod = MODULES.get("detect_and_install_packages")
    if not mod: return create_error_response("Detect and install packages module not loaded")
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)  # Could be StreamingResponse or JSON

@app.post("/api/create-zip")
async def api_create_zip():
    await sync_globals()
    mod = MODULES.get("create_zip")
    if not mod: return create_error_response("Create zip module not loaded")
    result = await maybe_await(mod.POST())
    return CustomJSONResponse(result)

@app.post("/api/run-command")
async def api_run_command(request: Request):
    await sync_globals()
    mod = MODULES.get("run_command")
    if not mod: return create_error_response("Run command module not loaded")
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)

@app.get("/api/sandbox-logs")
async def api_sandbox_logs():
    await sync_globals()
    mod = MODULES.get("sandbox_logs")
    if not mod: return create_error_response("Sandbox logs module not loaded")
    result = await maybe_await(mod.GET())
    return CustomJSONResponse(result)

@app.post("/api/analyze-edit-intent")
async def api_analyze_edit_intent(request: Request):
    await sync_globals()
    mod = MODULES.get("analyze_edit_intent")
    if not mod: return create_error_response("Analyze edit intent module not loaded")
    body = await request.json()
    result = await maybe_await(mod.POST(body))
    return CustomJSONResponse(result)


# --- Main Entrypoint ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"🚀 Backend ready and running on http://localhost:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)