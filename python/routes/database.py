import sqlite3
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager
import threading

# Thread-local storage for database connections
_local = threading.local()

# Database path - use persistent storage
DB_PATH = Path('/app/data') / 'sandbox_state.db'

def init_database():
    """Initialize the database with required tables"""
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sandbox_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                sandbox_id TEXT,
                url TEXT,
                active INTEGER DEFAULT 0,
                created_at INTEGER,
                updated_at INTEGER,
                metadata TEXT
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS conversation_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                state_data TEXT,
                updated_at INTEGER
            )
        ''')
        
        # Insert default row if not exists
        conn.execute('''
            INSERT OR IGNORE INTO sandbox_state (id, active) VALUES (1, 0)
        ''')
        
        conn.execute('''
            INSERT OR IGNORE INTO conversation_state (id, state_data) VALUES (1, '{}')
        ''')
        
        conn.commit()
        print("[database] Database initialized successfully")

@contextmanager
def get_connection():
    """Get a database connection with proper error handling"""
    if not hasattr(_local, 'connection') or _local.connection is None:
        _local.connection = sqlite3.connect(str(DB_PATH), timeout=30.0)
        _local.connection.row_factory = sqlite3.Row
    
    try:
        yield _local.connection
    except Exception as e:
        _local.connection.rollback()
        print(f"[database] Error: {e}")
        raise
    finally:
        # Don't close connection, keep it for reuse in thread
        pass

def close_connection():
    """Close the thread-local connection"""
    if hasattr(_local, 'connection') and _local.connection:
        _local.connection.close()
        _local.connection = None

def get_sandbox_state() -> Optional[Dict[str, Any]]:
    """Get current sandbox state from database"""
    try:
        with get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM sandbox_state WHERE id = 1'
            ).fetchone()
            
            if row and row['active'] and row['sandbox_id']:
                metadata = json.loads(row['metadata'] or '{}')
                return {
                    'sandboxId': row['sandbox_id'],
                    'url': row['url'],
                    'active': bool(row['active']),
                    'createdAt': row['created_at'],
                    'updatedAt': row['updated_at'],
                    **metadata
                }
    except Exception as e:
        print(f"[database] Error getting sandbox state: {e}")
    
    return None

def set_sandbox_state(state: Optional[Dict[str, Any]]):
    """Set sandbox state in database"""
    try:
        import time
        current_time = int(time.time() * 1000)
        
        with get_connection() as conn:
            if state:
                # Extract metadata (everything except core fields)
                core_fields = {'sandboxId', 'url', 'active', 'createdAt', 'updatedAt'}
                metadata = {k: v for k, v in state.items() if k not in core_fields}
                
                conn.execute('''
                    UPDATE sandbox_state 
                    SET sandbox_id = ?, url = ?, active = 1, 
                        created_at = COALESCE(created_at, ?), 
                        updated_at = ?, metadata = ?
                    WHERE id = 1
                ''', (
                    state.get('sandboxId'),
                    state.get('url'),
                    state.get('createdAt', current_time),
                    current_time,
                    json.dumps(metadata)
                ))
            else:
                # Clear state
                conn.execute('''
                    UPDATE sandbox_state 
                    SET sandbox_id = NULL, url = NULL, active = 0, 
                        updated_at = ?, metadata = '{}'
                    WHERE id = 1
                ''', (current_time,))
            
            conn.commit()
            print(f"[database] Sandbox state {'saved' if state else 'cleared'}")
    
    except Exception as e:
        print(f"[database] Error setting sandbox state: {e}")

def get_conversation_state() -> Dict[str, Any]:
    """Get conversation state from database"""
    try:
        with get_connection() as conn:
            row = conn.execute(
                'SELECT state_data FROM conversation_state WHERE id = 1'
            ).fetchone()
            
            if row and row['state_data']:
                return json.loads(row['state_data'])
    except Exception as e:
        print(f"[database] Error getting conversation state: {e}")
    
    return {}

def set_conversation_state(state: Dict[str, Any]):
    """Set conversation state in database"""
    try:
        import time
        with get_connection() as conn:
            conn.execute('''
                UPDATE conversation_state 
                SET state_data = ?, updated_at = ?
                WHERE id = 1
            ''', (json.dumps(state), int(time.time() * 1000)))
            conn.commit()
    except Exception as e:
        print(f"[database] Error setting conversation state: {e}")

# Initialize database on import
init_database()