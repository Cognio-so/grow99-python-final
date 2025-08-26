from typing import Any, Dict, Set, Optional
import sys
# from routes.state_manager import save_state

# Global variables to match TypeScript globals
active_sandbox: Optional[Any] = None
sandbox_data: Optional[Any] = None
existing_files: Set[str] = set()
import inspect
from routes.database import get_sandbox_state
async def POST() -> Dict[str, Any]:
    """Kill active sandbox - equivalent to POST function from TypeScript"""
    try:
        print('[kill-sandbox] Killing active sandbox...')
        
        # Kill existing sandbox if any (check database for active sandbox state)
        state = get_sandbox_state()
        if state and state.get("sandboxId"):
            # Use your sandbox SDK to close the active sandbox
            sandbox_id = state["sandboxId"]
            print(f"[kill-sandbox] Killing sandbox with ID: {sandbox_id}")
            # Example of sandbox cleanup logic:
            if sandbox_id:
                sandbox = E2BSandbox.connect(sandbox_id, api_key=os.getenv("E2B_API_KEY"))
                sandbox.close()  # Close the sandbox connection

        # Clear all global state variables in the database (not in memory)
        set_sandbox_state(None)

        # Clean up session files
        import os
        state_files = ['/tmp/g99_sandbox.json', '/tmp/g99_conversation_state.json']
        for state_file in state_files:
            if os.path.exists(state_file):
                os.remove(state_file)
                print(f"[kill-sandbox] Cleared {state_file}")

        return {"success": True, "sandboxKilled": True, "message": "Sandbox cleaned up successfully"}

    except Exception as error:
        print(f'[kill-sandbox] Error: {error}')
        return {"success": False, "error": str(error)}
