# routes/state_manager.py
import json
import os
from pathlib import Path
from typing import Any, Dict

# --- Project Paths ---
ROOT = Path(__file__).parent.parent.resolve()
STATE_FILE = ROOT / "state.json"

def save_state(modules: Dict[str, Any]):
    """
    Saves the critical global state from various modules to a single JSON file.
    """
    print("[state_manager] 💾 Saving application state...")
    try:
        state_to_save = {}
        
        # Extract state from create_ai_sandbox or sandbox_status
        # These modules hold the primary sandbox state
        sandbox_provider = modules.get("create_ai_sandbox") or modules.get("sandbox_status")
        if sandbox_provider:
            state_to_save["sandbox_data"] = getattr(sandbox_provider, "sandbox_data", None)
            state_to_save["existing_files"] = list(getattr(sandbox_provider, "existing_files", set()))
        
        # Extract state from conversation_state
        convo_provider = modules.get("conversation_state")
        if convo_provider and hasattr(convo_provider, "conversation_state"):
            convo_state = getattr(convo_provider, "conversation_state", None)
            if convo_state:
                state_to_save["conversation_state"] = convo_state.model_dump()

        with open(STATE_FILE, "w") as f:
            json.dump(state_to_save, f, indent=2)
            
        print(f"[state_manager] ✅ State successfully saved to {STATE_FILE}")
        
    except Exception as e:
        print(f"[state_manager] ❌ Error saving state: {e}")


def load_state(modules: Dict[str, Any]):
    """
    Loads the state from the JSON file and re-populates the globals in all relevant modules.
    """
    if not os.path.exists(STATE_FILE):
        print("[state_manager] No state file found, starting fresh.")
        return

    print(f"[state_manager] 💾 Loading application state from {STATE_FILE}...")
    try:
        with open(STATE_FILE, "r") as f:
            loaded_state = json.load(f)

        # Re-populate conversation state
        if "conversation_state" in loaded_state and modules.get("conversation_state"):
            from .conversation_state import ConversationStateModel # Local import to avoid circular dependency issues
            convo_module = modules["conversation_state"]
            try:
                convo_module.conversation_state = ConversationStateModel(**loaded_state["conversation_state"])
                print("[state_manager] ✅ Conversation state restored.")
            except Exception as e:
                print(f"[state_manager] ⚠️ Could not restore conversation state: {e}")

        # Data to be synced across all modules
        sync_data = {
            "sandbox_data": loaded_state.get("sandbox_data"),
            "existing_files": set(loaded_state.get("existing_files", [])),
            # active_sandbox itself is not saved, it must be reconnected if needed.
            # We just load the *data* about it.
        }

        # Distribute the loaded state to all modules
        for module_name, module in modules.items():
            for key, value in sync_data.items():
                if hasattr(module, key):
                    setattr(module, key, value)
        
        print("[state_manager] ✅ Sandbox data and file lists restored.")

    except Exception as e:
        print(f"[state_manager] ❌ Error loading state: {e}")