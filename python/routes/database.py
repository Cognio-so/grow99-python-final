import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager
import threading
import time
import os  # <-- Make sure os is imported

# Enhanced environment detection with detailed logging
render_env = os.getenv('RENDER') == 'true'
print(f"[database] Environment: {'Render' if render_env else 'Local'}")
print(f"[database] RENDER env var: {os.getenv('RENDER')}")

if render_env:
    storage_path = Path('/app/data')
    print(f"[database] Render environment detected, using: {storage_path}")
    
    # Verify persistent disk mounting
    try:
        storage_path.mkdir(parents=True, exist_ok=True)
        test_file = storage_path / 'render_test.tmp'
        test_file.write_text('render_test')
        test_file.unlink()
        print(f"[database] Render storage is writable: {storage_path}")
    except Exception as e:
        print(f"[database] WARNING: Render storage issue: {e}")
        # Fallback to temp storage
        storage_path = Path('/tmp/growth99_data')
        storage_path.mkdir(parents=True, exist_ok=True)
        print(f"[database] Fallback to temp storage: {storage_path}")
else:
    storage_path = Path(__file__).resolve().parent.parent / 'local_data'
    storage_path.mkdir(parents=True, exist_ok=True)
    print(f"[database] Local environment detected, using: {storage_path}")

DB_PATH = storage_path / 'sandbox_state.db'
print(f"[database] Final database path: {DB_PATH}")
# --- END OF NEW LOGIC ---


# Thread-local storage for database connections
_local = threading.local()

# ... (the rest of your database.py file remains the same) ...

def get_schema_version(conn):
    try:
        cursor = conn.execute("PRAGMA user_version")
        return cursor.fetchone()[0]
    except:
        return 0

def set_schema_version(conn, version):
    conn.execute(f"PRAGMA user_version = {version}")

def migrate_database(conn):
    current_version = get_schema_version(conn)
    
    if current_version < 1:
        print("[database] Migrating to version 1: Adding session tracking columns...")
        try:
            conn.execute('ALTER TABLE sandbox_state ADD COLUMN last_activity INTEGER')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e): print(f"[database] Warning: {e}")
        try:
            conn.execute('ALTER TABLE sandbox_state ADD COLUMN session_id TEXT')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e): print(f"[database] Warning: {e}")
        try:
            conn.execute('ALTER TABLE sandbox_state ADD COLUMN user_ip TEXT')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e): print(f"[database] Warning: {e}")
        try:
            conn.execute('ALTER TABLE conversation_state ADD COLUMN session_id TEXT')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e): print(f"[database] Warning: {e}")
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS cleanup_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sandbox_id TEXT,
                cleanup_time INTEGER, cleanup_reason TEXT, success INTEGER
            )
        ''')
        set_schema_version(conn, 1)
        print("[database] Migration to version 1 complete")

def init_database():
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sandbox_state (
                id INTEGER PRIMARY KEY CHECK (id = 1), sandbox_id TEXT, url TEXT,
                active INTEGER DEFAULT 0, created_at INTEGER, updated_at INTEGER,
                metadata TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS conversation_state (
                id INTEGER PRIMARY KEY CHECK (id = 1), state_data TEXT, updated_at INTEGER
            )
        ''')
        conn.execute('INSERT OR IGNORE INTO sandbox_state (id, active) VALUES (1, 0)')
        conn.execute("INSERT OR IGNORE INTO conversation_state (id, state_data) VALUES (1, '{}')")
        
        migrate_database(conn)
        
        conn.commit()
        print("[database] Enhanced database initialized successfully")

@contextmanager
def get_connection():
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
        pass

def close_connection():
    if hasattr(_local, 'connection') and _local.connection:
        _local.connection.close()
        _local.connection = None

def get_sandbox_state() -> Optional[Dict[str, Any]]:
    try:
        with get_connection() as conn:
            row = conn.execute('SELECT * FROM sandbox_state WHERE id = 1').fetchone()
            if row and row['active'] and row['sandbox_id']:
                metadata = json.loads(row['metadata'] or '{}')
                return {
                    'sandboxId': row['sandbox_id'], 'url': row['url'],
                    'active': bool(row['active']), 'createdAt': row['created_at'],
                    'updatedAt': row['updated_at'],
                    'lastActivity': row['last_activity'] if 'last_activity' in row.keys() else None,
                    'sessionId': row['session_id'] if 'session_id' in row.keys() else None,
                    'userIP': row['user_ip'] if 'user_ip' in row.keys() else None,
                    **metadata
                }
    except Exception as e:
        print(f"[database] Error getting sandbox state: {e}")
    return None

def set_sandbox_state(state: Optional[Dict[str, Any]], user_ip: str = None, session_id: str = None):
    try:
        current_time = int(time.time() * 1000)
        
        # ENHANCED LOGGING
        if state:
            print(f"[database] CREATING sandbox: {state.get('sandboxId')} on {'Render' if os.getenv('RENDER') == 'true' else 'Local'}")
            print(f"[database] Sandbox URL: {state.get('url')}")
            print(f"[database] User IP: {user_ip}")
        else:
            print(f"[database] DELETING sandbox on {'Render' if os.getenv('RENDER') == 'true' else 'Local'}")
        
        with get_connection() as conn:
            if state:
                core_fields = {'sandboxId', 'url', 'active', 'createdAt', 'updatedAt', 'lastActivity', 'sessionId', 'userIP'}
                metadata = {k: v for k, v in state.items() if k not in core_fields}
                if not session_id:
                    import uuid
                    session_id = str(uuid.uuid4())
                
                conn.execute('''
                    UPDATE sandbox_state SET sandbox_id = ?, url = ?, active = 1, 
                        created_at = COALESCE(created_at, ?), updated_at = ?, last_activity = ?,
                        session_id = ?, user_ip = ?, metadata = ? WHERE id = 1
                ''', (
                    state.get('sandboxId'), state.get('url'), state.get('createdAt', current_time),
                    current_time, current_time, session_id, user_ip, json.dumps(metadata)
                ))
                print(f"[database] Sandbox {state.get('sandboxId')} saved to database")
            else:
                cursor = conn.execute('SELECT sandbox_id FROM sandbox_state WHERE id = 1')
                row = cursor.fetchone()
                old_sandbox_id = row['sandbox_id'] if row else None
                if old_sandbox_id:
                    conn.execute('''
                        INSERT INTO cleanup_log (sandbox_id, cleanup_time, cleanup_reason, success)
                        VALUES (?, ?, ?, ?)
                    ''', (old_sandbox_id, current_time, 'manual_cleanup', 1))
                    print(f"[database] Logged cleanup of sandbox: {old_sandbox_id}")
                
                conn.execute('''
                    UPDATE sandbox_state SET sandbox_id = NULL, url = NULL, active = 0, 
                        updated_at = ?, last_activity = NULL, session_id = NULL,
                        user_ip = NULL, metadata = '{}' WHERE id = 1
                ''', (current_time,))
                print(f"[database] Sandbox state cleared from database")
            
            conn.commit()
    except Exception as e:
        print(f"[database] ERROR setting sandbox state: {e}")

def update_activity():
    try:
        current_time = int(time.time() * 1000)
        with get_connection() as conn:
            conn.execute('UPDATE sandbox_state SET last_activity = ?, updated_at = ? WHERE id = 1 AND active = 1',
                         (current_time, current_time))
            conn.commit()
    except Exception as e:
        print(f"[database] Error updating activity: {e}")

def get_conversation_state() -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            row = conn.execute('SELECT state_data FROM conversation_state WHERE id = 1').fetchone()
            if row and row['state_data']:
                return json.loads(row['state_data'])
    except Exception as e:
        print(f"[database] Error getting conversation state: {e}")
    return {}

def set_conversation_state(state: Dict[str, Any]):
    try:
        with get_connection() as conn:
            conn.execute('UPDATE conversation_state SET state_data = ?, updated_at = ? WHERE id = 1',
                         (json.dumps(state), int(time.time() * 1000)))
            conn.commit()
    except Exception as e:
        print(f"[database] Error setting conversation state: {e}")

def get_cleanup_stats():
    try:
        with get_connection() as conn:
            row = conn.execute('''
                SELECT COUNT(*) as total_cleanups, SUM(success) as successful_cleanups,
                       MAX(cleanup_time) as last_cleanup
                FROM cleanup_log WHERE cleanup_time > ?
            ''', (int(time.time() * 1000) - 86400000,)).fetchone()
            return {
                'totalCleanups': row['total_cleanups'] if row else 0,
                'successfulCleanups': row['successful_cleanups'] if row else 0,
                'lastCleanup': row['last_cleanup'] if row else None
            }
    except Exception as e:
        print(f"[database] Error getting cleanup stats: {e}")
        return {}

init_database()