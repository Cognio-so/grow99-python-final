from datetime import datetime
import json
import inspect

try:
    from e2b_code_interpreter import Sandbox as E2BSandbox
    SDK_TYPE = "code_interpreter"
except Exception:
    try:
        from e2b import Sandbox as E2BSandbox
        SDK_TYPE = "legacy"
    except Exception:
        E2BSandbox = None
        SDK_TYPE = None

# Global variables (similar to those in TypeScript)
active_sandbox = None
sandbox_data = None
existing_files = set()

def get_sandbox_status():
    """
    Get the status of the sandbox, similar to the TypeScript GET route functionality.
    Returns JSON-serializable dictionary with sandbox status information.
    """
    try:
        # Check if sandbox exists
        sandbox_exists = active_sandbox is not None
        
        sandbox_healthy = False
        sandbox_info = None
        
        if sandbox_exists and active_sandbox:
            try:
                # Retrieve sandbox information
                info = active_sandbox.get_info()
                
                sandbox_healthy = True
                sandbox_info = {
                    "sandboxId": sandbox_data.get("sandboxId") if sandbox_data else None,
                    "url": sandbox_data.get("url") if sandbox_data else None,
                    "filesTracked": list(existing_files) if existing_files else [],
                    "lastHealthCheck": datetime.now().isoformat()
                }
            except Exception as error:
                print(f"[sandbox-status] Health check failed: {error}")
                sandbox_healthy = False
        
        return {
            "success": True,
            "active": sandbox_exists,
            "healthy": sandbox_healthy,
            "sandboxData": sandbox_info,
            "message": "Sandbox is active and healthy" if sandbox_healthy 
                      else "Sandbox exists but is not responding" if sandbox_exists 
                      else "No active sandbox"
        }
        
    except Exception as error:
        print(f"[sandbox-status] Error: {error}")
        return {
            "success": False,
            "active": False,
            "error": str(error)
        }
from dotenv import load_dotenv
import os
import re
import json
def initialize_sandbox(timeout_seconds=60):
    """
    Initialize a new sandbox instance
    """
    global active_sandbox, sandbox_data, existing_files
    
    try:
        # Create sandbox with specified timeout
        api_key=os.getenv("E2B_API_KEY")
        create_fn = getattr(E2BSandbox, "create", None)

        if create_fn and inspect.iscoroutinefunction(create_fn):
            # If this code path is inside a sync function, either:
            # 1) move creation to an async context and 'await' it there, OR
            # 2) wrap it with asyncio.run(...) exactly once at startup.
            # Example (only if you're at module start or a CLI entrypoint):
            # active_sandbox = asyncio.run(create_fn(api_key=api_key, timeout=timeout_seconds))
            raise RuntimeError("sandbox_status.py is synchronous; create() here is async. Create the sandbox in your async route and only 'read' status here.")
        elif create_fn:
            active_sandbox = create_fn(api_key=api_key, timeout=timeout_seconds)
        else:
            active_sandbox = E2BSandbox(api_key=api_key, timeout=timeout_seconds)

        
        # Get sandbox info
        info = active_sandbox.get_info()
        
        # Store sandbox data
        sandbox_data = {
            "sandboxId": info.sandbox_id,
            "templateId": info.template_id,
            "name": info.name,
            "startedAt": info.started_at.isoformat(),
            "endAt": info.end_at.isoformat(),
            "url": None  # The URL field might need to be populated from elsewhere
        }
        
        existing_files = set()
        
        return {
            "success": True,
            "message": "Sandbox initialized successfully",
            "sandboxInfo": sandbox_data
        }
        
    except Exception as error:
        print(f"[initialize-sandbox] Error: {error}")
        return {
            "success": False,
            "error": str(error)
        }

# Example usage
if __name__ == "__main__":
    # Initialize a sandbox
    init_result = initialize_sandbox()
    print(json.dumps(init_result, indent=2))
    
    if init_result["success"]:
        # Get status after initialization
        status = get_sandbox_status()
        print(json.dumps(status, indent=2))
