import json
import os
from filelock import FileLock, Timeout  # MODIFIED: Use the cross-platform filelock library
from typing import Optional, Dict, Any

STATE_FILE_PATH = '/tmp/g99_sandbox_state.json'
# Define a separate lock file path; this is standard practice
LOCK_FILE_PATH = '/tmp/g99_sandbox_state.json.lock'


def get_sandbox_state() -> Optional[Dict[str, Any]]:
    """
    Reads the current sandbox state from the centralized file in a process-safe way.
    Returns None if no state exists.
    """
    lock = FileLock(LOCK_FILE_PATH, timeout=5)
    try:
        # Create the /tmp directory if it doesn't exist (useful for Windows)
        os.makedirs(os.path.dirname(STATE_FILE_PATH), exist_ok=True)

        if not os.path.exists(STATE_FILE_PATH):
            return None
        
        with lock:
            with open(STATE_FILE_PATH, 'r') as f:
                state = json.load(f)
        
        if state and state.get('active'):
            return state
        return None
    except (IOError, json.JSONDecodeError, KeyError, Timeout):
        # Timeout happens if the lock can't be acquired
        return None

def set_sandbox_state(state: Optional[Dict[str, Any]]):
    """
    Writes the sandbox state to the centralized file in a process-safe way.
    Pass None to clear the state.
    """
    lock = FileLock(LOCK_FILE_PATH, timeout=5)
    try:
        # Create the /tmp directory if it doesn't exist
        os.makedirs(os.path.dirname(STATE_FILE_PATH), exist_ok=True)

        with lock:
            with open(STATE_FILE_PATH, 'w') as f:
                if state:
                    state['active'] = True
                    json.dump(state, f, indent=2)
                else:
                    json.dump({"active": False, "sandboxId": None, "url": None}, f)
    except (IOError, Timeout) as e:
        print(f"[state_manager] Error writing state file: {e}")