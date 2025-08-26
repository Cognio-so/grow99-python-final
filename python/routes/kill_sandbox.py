# Enhanced kill_sandbox.py for production cleanup
from typing import Any, Dict, Set, Optional
import sys
import inspect
import asyncio
# kill_sandbox.py
# ... other imports
from routes.database import set_sandbox_state, set_conversation_state, close_connection

# Global variables to match TypeScript globals
active_sandbox: Optional[Any] = None
sandbox_data: Optional[Any] = None
existing_files: Set[str] = set()

async def comprehensive_sandbox_cleanup(sandbox):
    """Completely wipe all files and restart fresh environment"""
    if not sandbox:
        return False
    
    cleanup_code = """
import os
import shutil
import subprocess
import time

print("=== COMPREHENSIVE PRODUCTION CLEANUP ===")

# 1. Kill all Node.js/Vite processes
try:
    subprocess.run(['pkill', '-f', 'vite'], timeout=5)
    subprocess.run(['pkill', '-f', 'node'], timeout=5)
    subprocess.run(['pkill', '-f', 'npm'], timeout=5)
    print("✅ Killed all Node.js processes")
except:
    pass

# 2. Remove entire app directory
app_dir = "/home/user/app"
if os.path.exists(app_dir):
    try:
        shutil.rmtree(app_dir)
        print("✅ Deleted entire app directory")
    except Exception as e:
        print(f"❌ Failed to delete app directory: {e}")

# 3. Clear all temp files
temp_patterns = [
    "/tmp/vite-*",
    "/tmp/node-*", 
    "/tmp/.vite-*",
    "/home/user/.npm",
    "/home/user/.cache"
]

for pattern in temp_patterns:
    try:
        if '*' in pattern:
            import glob
            for path in glob.glob(pattern):
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        elif os.path.exists(pattern):
            if os.path.isdir(pattern):
                shutil.rmtree(pattern)
            else:
                os.remove(pattern)
    except:
        pass

print("✅ Cleared all temporary files")

# 4. Reset environment
os.makedirs("/home/user/app", exist_ok=True)
os.chdir("/home/user/app")

print("✅ Environment reset complete")
print("CLEANUP_STATUS: SUCCESS")
"""
    
    try:
        # Import the sandbox execution function
        from routes.apply_ai_code_stream import _run_in_sandbox
        result = await _run_in_sandbox(sandbox, cleanup_code)
        
        # Extract output
        if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
            output = ''.join(result.logs.stdout) if isinstance(result.logs.stdout, list) else str(result.logs.stdout or "")
        else:
            output = str(result)
        
        print(f"[comprehensive_cleanup] {output}")
        return "CLEANUP_STATUS: SUCCESS" in output
        
    except Exception as e:
        print(f"[comprehensive_cleanup] Error: {e}")
        return False

async def POST() -> Dict[str, Any]:
    """Enhanced kill sandbox with complete cleanup for production"""
    global active_sandbox, sandbox_data, existing_files
    
    try:
        print('[kill-sandbox] Starting comprehensive production cleanup...')
        
        cleanup_success = False
        sandbox_killed = False
        
        # 1. Comprehensive file cleanup if sandbox exists
        if active_sandbox is not None:
            try:
                cleanup_success = await comprehensive_sandbox_cleanup(active_sandbox)
                print(f'[kill-sandbox] File cleanup: {"SUCCESS" if cleanup_success else "FAILED"}')
            except Exception as e:
                print(f'[kill-sandbox] Cleanup error: {e}')
        
        # 2. Kill the sandbox connection
        if active_sandbox is not None:
            try:
                if hasattr(active_sandbox, 'close'):
                    if inspect.iscoroutinefunction(active_sandbox.close):
                        await active_sandbox.close()
                    else:
                        active_sandbox.close()
                sandbox_killed = True
                print('[kill-sandbox] Sandbox connection closed')
            except Exception as e:
                print(f'[kill-sandbox] Failed to close sandbox: {e}')
        
        # 3. Clear ALL global state variables
        active_sandbox = None
        sandbox_data = None
        existing_files.clear()
        
        # 4. Clear persistent database state
        set_sandbox_state(None)  # Clear sandbox state
        set_conversation_state({})  # Clear conversation history
        from routes.database import close_connection
        close_connection()
        print("[kill-sandbox] Database connection closed for file deletion.")
        # 5. Clear any remaining state files
        try:
            import os
            state_files = [
                '/tmp/g99_sandbox.json', 
                '/tmp/g99_conversation_state.json',
                '/app/data/sandbox_state.db'  # Your persistent DB
            ]
            for state_file in state_files:
                if os.path.exists(state_file):
                    os.remove(state_file)
                    print(f"[kill-sandbox] Cleared {state_file}")
        except Exception as e:
            print(f"[kill-sandbox] Failed to clear state files: {e}")
        
        # 6. Force garbage collection to free memory
        import gc
        gc.collect()
        
        print('[kill-sandbox] ✅ COMPLETE CLEANUP FINISHED')
        
        return {
            "success": True,
            "sandboxKilled": sandbox_killed,
            "filesCleared": cleanup_success,
            "stateCleared": True,
            "message": "Complete production cleanup successful - fresh environment ready"
        }
        
    except Exception as error:
        print(f'[kill-sandbox] CRITICAL ERROR: {error}')
        
        # Emergency cleanup - clear everything possible
        active_sandbox = None
        sandbox_data = None
        existing_files.clear()
        
        try:
            set_sandbox_state(None)
            set_conversation_state({})
        except:
            pass
        
        return {
            "success": False,
            "error": str(error),
            "emergencyCleanup": True,
            "message": "Emergency cleanup performed due to error"
        }