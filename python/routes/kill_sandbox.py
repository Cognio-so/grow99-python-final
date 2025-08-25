from typing import Any, Dict, Set, Optional
import sys
from routes.state_manager import save_state

# Global variables to match TypeScript globals
active_sandbox: Optional[Any] = None
sandbox_data: Optional[Any] = None
existing_files: Set[str] = set()
import inspect
async def POST() -> Dict[str, Any]:
    """Kill active sandbox - equivalent to POST function from TypeScript"""
    global active_sandbox, sandbox_data, existing_files
    
    try:
        print('[kill-sandbox] Killing active sandbox...')
        
        sandbox_killed = False
        
        # Kill existing sandbox if any
        if active_sandbox is not None:
            try:
                if hasattr(active_sandbox, 'close'):
                    if inspect.iscoroutinefunction(active_sandbox.close):
                        await active_sandbox.close()
                    else:
                        active_sandbox.close()
                sandbox_killed = True
                print('[kill-sandbox] Sandbox closed successfully')
            except Exception as e:
                print(f'[kill-sandbox] Failed to close sandbox: {e}')

            
        # Clear all global state variables
        active_sandbox = None
        sandbox_data = None
        existing_files.clear()
        
        # --- SAVE THE CLEARED STATE ---
        # main_app = sys.modules.get("main")
        # if main_app and hasattr(main_app, "MODULES"):
        #     save_state(main_app.MODULES)
        # # ----------------------------
        
        return {
            "success": True,
            "sandboxKilled": sandbox_killed,
            "message": "Sandbox cleaned up successfully"
        }
        
    except Exception as error:
        print(f'[kill-sandbox] Error: {error}')
        return {
            "success": False,
            "error": str(error)
        }