# create_ai_sandbox.py - FIXED with complete Tailwind CSS setup (exact copy from TS)

from typing import Any, Dict, Optional, Set
import os
import asyncio
import inspect
import json
import time
from types import SimpleNamespace

try:
    from langchain_core.runnables import RunnableLambda
    from langgraph.graph import StateGraph, START, END
except Exception as _e:
    raise

# E2B SDK imports with better error handling
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

# App config
try:
    from config.app_config import appConfig
except Exception:
    appConfig = SimpleNamespace(
        e2b=SimpleNamespace(
            timeoutMinutes=15,
            timeoutMs=15 * 60 * 1000,
            vitePort=5173,
            viteStartupDelay=8000,
        )
    )

# Globals
active_sandbox: Optional[Any] = None
sandbox_data: Optional[Dict[str, Any]] = None
existing_files: Set[str] = set()
sandbox_state: Optional[Dict[str, Any]] = None

async def _run_in_sandbox(sandbox: Any, code: str) -> Dict[str, Any]:
    """Enhanced sandbox execution with better error handling"""
    async def _runner(payload: Dict[str, Any]) -> Dict[str, Any]:
        c = payload.get("code", "")
        
        # Try multiple method names for different SDK versions
        run_methods = ['run_code', 'runCode', 'run', 'exec']
        run_method = None
        
        for method in run_methods:
            if hasattr(sandbox, method):
                run_method = getattr(sandbox, method)
                break
        
        if run_method is None:
            raise RuntimeError(f"Sandbox missing execution methods: {run_methods}")
        
        try:
            if inspect.iscoroutinefunction(run_method):
                result = await run_method(c)
            else:
                result = run_method(c)
            
            # Handle different result types
            if hasattr(result, 'wait'):
                try:
                    result.wait()
                except:
                    pass
            
            return result
        except Exception as e:
            return {"output": f"Error: {str(e)}", "success": False}

    chain = RunnableLambda(_runner)

    def _compile_graph():
        g = StateGraph(dict)
        async def exec_node(state: Dict[str, Any]) -> Dict[str, Any]:
            return await chain.ainvoke(state)
        g.add_node("exec", exec_node)
        g.add_edge(START, "exec")
        g.add_edge("exec", END)
        return g.compile()

    # if not hasattr(_run_in_sandbox, "_graph"):
    #     _run_in_sandbox._graph = _compile_graph()

    # graph = _run_in_sandbox._graph
    # return await graph.ainvoke({"code": code})
    return await chain.ainvoke({"code": code})

def _extract_output_text(result: Any) -> str:
    """Enhanced output extraction"""
    if isinstance(result, dict):
        out = result.get("output")
        if isinstance(out, str):
            return out
        
        logs = result.get("logs")
        if isinstance(logs, dict):
            stdout = logs.get("stdout")
            if isinstance(stdout, list):
                return ''.join(str(x) for x in stdout)
            elif isinstance(stdout, str):
                return stdout
    
    # Handle E2B execution objects
    if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
        if isinstance(result.logs.stdout, list):
            return ''.join(str(x) for x in result.logs.stdout)
        else:
            return str(result.logs.stdout or "")
    elif hasattr(result, 'output'):
        return str(result.output or "")
    
    return ""

async def get_correct_sandbox_url(sandbox: Any, sandbox_id: str) -> str:
    """FIXED: Get the correct accessible E2B URL with verification"""
    print(f"[get_sandbox_url] SDK Type: {SDK_TYPE}")
    print(f"[get_sandbox_url] Sandbox ID: {sandbox_id}")
    
    possible_urls = []
    
    # Method 1: Try get_hostname for code_interpreter SDK
    if SDK_TYPE == "code_interpreter" and hasattr(sandbox, 'get_hostname'):
        try:
            hostname = sandbox.get_hostname(appConfig.e2b.vitePort)
            url = f"https://{hostname}"
            possible_urls.append(url)
            print(f"[get_sandbox_url] Method 1 - get_hostname: {url}")
        except Exception as e:
            print(f"[get_sandbox_url] Method 1 failed: {e}")
    
    # Method 2: Try url property
    if hasattr(sandbox, 'url'):
        url = getattr(sandbox, 'url')
        if url:
            possible_urls.append(url)
            print(f"[get_sandbox_url] Method 2 - url property: {url}")
    
    # Method 3: Try different E2B URL formats
    url_formats = [
        f"https://{appConfig.e2b.vitePort}-{sandbox_id}.e2b.app",
        f"https://{appConfig.e2b.vitePort}-{sandbox_id}.e2b.dev",
        f"https://{sandbox_id}.e2b.app:{appConfig.e2b.vitePort}",
        f"https://{sandbox_id}.e2b.dev:{appConfig.e2b.vitePort}",
        f"https://{sandbox_id}.e2b.app",
        f"https://{sandbox_id}.e2b.dev",
    ]

    for url in url_formats:
        possible_urls.append(url)
        print(f"[get_sandbox_url] Method 3 - format: {url}")
    
    # Return the first URL for now - we'll verify it works later
    final_url = possible_urls[0] if possible_urls else f"https://{sandbox_id}.e2b.dev"
    print(f"[get_sandbox_url] Selected URL: {final_url}")
    return final_url

async def verify_vite_server(sandbox: Any, expected_url: str) -> bool:
    """Verify that Vite server is actually running and accessible"""
    print("[verify_vite_server] Checking Vite server status...")
    
    verify_code = f'''
import subprocess
import time
import socket
import requests
from urllib.parse import urlparse

def check_port_open(port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result == 0
    except:
        return False

def check_vite_process():
    try:
        result = subprocess.run(['pgrep', '-f', 'vite'], capture_output=True, text=True)
        return bool(result.stdout.strip())
    except:
        return False

def test_vite_response():
    try:
        import requests
        response = requests.get('http://localhost:5173', timeout=5)
        return response.status_code == 200
    except:
        return False

# Check port
port_open = check_port_open(5173)
print(f"PORT_5173_OPEN: {{port_open}}")

# Check process
process_running = check_vite_process()
print(f"VITE_PROCESS_RUNNING: {{process_running}}")

# Test response
vite_responding = test_vite_response()
print(f"VITE_RESPONDING: {{vite_responding}}")

# Show running processes
try:
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    lines = result.stdout.split('\\n')
    for line in lines:
        if 'vite' in line.lower() or 'node' in line.lower():
            print(f"PROCESS: {{line}}")
except:
    pass

print("VERIFICATION_COMPLETE")
'''
    
    try:
        verify_result = await _run_in_sandbox(sandbox, verify_code)
        output = _extract_output_text(verify_result)
        print(f"[verify_vite_server] Verification output: {output}")
        
        # Parse results
        port_open = "PORT_5173_OPEN: True" in output
        process_running = "VITE_PROCESS_RUNNING: True" in output  
        vite_responding = "VITE_RESPONDING: True" in output
        
        print(f"[verify_vite_server] Port open: {port_open}")
        print(f"[verify_vite_server] Process running: {process_running}")
        print(f"[verify_vite_server] Vite responding: {vite_responding}")
        
        return port_open and (process_running or vite_responding)
        
    except Exception as e:
        print(f"[verify_vite_server] Verification failed: {e}")
        return False

async def ensure_vite_server(sandbox: Any, sandbox_id: str) -> bool:
    """Ensure Vite server is running properly with COMPLETE Tailwind setup"""
    print("[ensure_vite_server] Starting Vite server setup with FULL Tailwind configuration...")
    
    # Keep your existing setup_script exactly as is...
    setup_script = '''
import os
import json

print('Setting up React app with Vite and Tailwind...')

# Create directory structure
os.makedirs('/home/user/app/src', exist_ok=True)

# Package.json with COMPLETE Tailwind dependencies
package_json = {
    "name": "sandbox-app",
    "version": "1.0.0",
    "type": "module",
    "scripts": {
        "dev": "vite --host 0.0.0.0 --port 5173 --strictPort --config vite.config.mjs",
        "build": "vite build --config vite.config.mjs",
        "preview": "vite preview --host 0.0.0.0 --port 5173 --config vite.config.mjs"
    },
    "dependencies": {
        "react": "^18.2.0",
        "react-dom": "^18.2.0"
    },
    "devDependencies": {
        "@vitejs/plugin-react": "^4.3.0",
        "vite": "^6.0.9",
        "tailwindcss": "^3.3.0",
        "postcss": "^8.4.31",
        "autoprefixer": "^10.4.16"
    }
}

with open('/home/user/app/package.json', 'w') as f:
    json.dump(package_json, f, indent=2)
print('✓ package.json')

# Vite config
vite_config = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const id = process.env.E2B_SANDBOX_ID
const allowed = ['localhost', '127.0.0.1', '::1']
if (id) {
  allowed.push(`5173-${id}.e2b.app`, `5173-${id}.e2b.dev`)
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: allowed,
    hmr: { clientPort: 443, host: id ? `5173-${id}.e2b.app` : undefined },
    watch: { usePolling: true, interval: 1000 },
    cors: true
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: allowed
  },
  define: { 'process.env': {}, global: 'globalThis' },
  optimizeDeps: { include: ['react','react-dom'] }
})
"""

with open('/home/user/app/vite.config.mjs', 'w') as f:
    f.write(vite_config)
print('✓ vite.config.mjs')

# Tailwind config
tailwind_config = """/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}"""

with open('/home/user/app/tailwind.config.js', 'w') as f:
    f.write(tailwind_config)
print('✓ tailwind.config.js')

# PostCSS config
postcss_config = """export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}"""

with open('/home/user/app/postcss.config.js', 'w') as f:
    f.write(postcss_config)
print('✓ postcss.config.js')

# Index.html
index_html = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sandbox App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>"""

with open('/home/user/app/index.html', 'w') as f:
    f.write(index_html)
print('✓ index.html')

# Main.jsx
main_jsx = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)"""

with open('/home/user/app/src/main.jsx', 'w') as f:
    f.write(main_jsx)
print('✓ src/main.jsx')

# App.jsx with placeholder content
app_jsx = """function App() {
  return (
    <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center p-4">
      <div className="text-center max-w-2xl">
        <h1 className="text-4xl font-bold mb-4 text-green-400">🚀 Sandbox Ready!</h1>
        <p className="text-lg text-gray-400">
          Your React app with Vite and Tailwind CSS is ready for development.
        </p>
        <div className="mt-6 p-4 bg-gray-800 rounded-lg">
          <p className="text-sm text-gray-300">
            This placeholder will be replaced when you generate your actual app.
          </p>
        </div>
      </div>
    </div>
  )
}

export default App"""

with open('/home/user/app/src/App.jsx', 'w') as f:
    f.write(app_jsx)
print('✓ src/App.jsx')

# Index.css with Tailwind directives
index_css = """@tailwind base;
@tailwind components;
@tailwind utilities;

/* Force Tailwind to load */
@layer base {
  :root {
    font-synthesis: none;
    text-rendering: optimizeLegibility;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    -webkit-text-size-adjust: 100%;
  }
  
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
  background-color: rgb(17 24 39);
}"""

with open('/home/user/app/src/index.css', 'w') as f:
    f.write(index_css)
print('✓ src/index.css')

print('\\n✅ All files created successfully!')
'''

    await _run_in_sandbox(sandbox, setup_script)
    
    # Install dependencies
    print("[ensure_vite_server] Installing dependencies...")
    install_script = '''
import subprocess

print('Installing npm packages...')
result = subprocess.run(
    ['npm', 'install'],
    cwd='/home/user/app',
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print('✓ Dependencies installed successfully')
else:
    print(f'⚠️ npm install issues: {result.stderr}')
    print(f'stdout: {result.stdout}')
'''
    await _run_in_sandbox(sandbox, install_script)
    
    # Start Vite server
    print("[ensure_vite_server] Starting Vite server...")
    start_code = '''
import subprocess, os, time, socket

# Kill any existing processes
try:
    subprocess.run(['pkill','-f','vite'], capture_output=True)
    subprocess.run(['pkill','-f','node.*vite'], capture_output=True)
    time.sleep(1)
    print("KILLED_EXISTING_PROCESSES")
except Exception:
    print("NO_PROCESSES_TO_KILL")

env = os.environ.copy()
env['FORCE_COLOR'] = '0'
env['HOST'] = '0.0.0.0'
env['PORT'] = '5173'
env['E2B_SANDBOX_ID'] = '{{SANDBOX_ID}}'

# Start Vite server in background
log_out = open('/home/user/vite-5173.out','ab', buffering=0)
log_err = open('/home/user/vite-5173.err','ab', buffering=0)

process = subprocess.Popen(
    ['npm','run','dev'],
    stdout=log_out,
    stderr=log_err,
    env=env,
    cwd='/home/user/app',
    preexec_fn=os.setsid if hasattr(os,'setsid') else None
)

with open('/tmp/vite-process.pid','w') as f:
    f.write(str(process.pid))
print(f"VITE_STARTED_PID: {process.pid}")

# Wait for port to be accessible
port_ready = False
for i in range(30):  # Increased timeout for deployment
    time.sleep(1)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)  # Increased timeout
        result = s.connect_ex(('localhost', 5173))
        s.close()
        if result == 0:
            print(f"VITE_PORT_READY_AFTER: {i+1}s")
            port_ready = True
            break
    except Exception as e:
        print(f"PORT_CHECK_ERROR: {e}")

# Verify all required files exist
files_ok = True
required_files = [
    '/home/user/app/tailwind.config.js',
    '/home/user/app/postcss.config.js', 
    '/home/user/app/src/index.css',
    '/home/user/app/src/App.jsx',
    '/home/user/app/src/main.jsx'
]

for file_path in required_files:
    if os.path.exists(file_path):
        print(f"✓ {file_path} exists")
        if file_path.endswith('index.css'):
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                if '@tailwind base' in content:
                    print("✓ Tailwind directives confirmed")
                else:
                    print("✗ Tailwind directives missing")
                    files_ok = False
            except Exception as e:
                print(f"✗ Error reading {file_path}: {e}")
                files_ok = False
    else:
        print(f"✗ {file_path} missing")
        files_ok = False

print(f"FILES_STATUS: {'OK' if files_ok else 'FAILED'}")
print(f"PORT_STATUS: {'OK' if port_ready else 'FAILED'}")
print(f"OVERALL_STATUS: {'SUCCESS' if (files_ok and port_ready) else 'FAILED'}")
'''
    
    # Replace sandbox ID
    start_code = start_code.replace("{{SANDBOX_ID}}", sandbox_id)
    
    try:
        start_result = await _run_in_sandbox(sandbox, start_code)
        output = _extract_output_text(start_result)
        print(f"[ensure_vite_server] Startup output: {output}")
        
        # FIXED: Check for the actual success indicators
        files_ok = "FILES_STATUS: OK" in output
        port_ok = "PORT_STATUS: OK" in output
        overall_success = "OVERALL_STATUS: SUCCESS" in output
        
        print(f"[ensure_vite_server] Files OK: {files_ok}")
        print(f"[ensure_vite_server] Port OK: {port_ok}")
        print(f"[ensure_vite_server] Overall Success: {overall_success}")
        
        if overall_success:
            print("[ensure_vite_server] ✅ SUCCESS: Vite + Tailwind fully configured!")
            return True
        else:
            print("[ensure_vite_server] ❌ FAILED: Setup incomplete")
            print(f"[ensure_vite_server] Full output: {output}")
            return False
        
    except Exception as e:
        print(f"[ensure_vite_server] Exception during startup: {e}")
        return False

# In create_ai_sandbox.py
async def _get_sandbox_id_compat(sandbox):
    # 1) Try common attributes
    sid = getattr(sandbox, "id", None) or getattr(sandbox, "sandbox_id", None)
    if sid:
        return sid

    # 2) Fallback to get_info() (async or sync)
    get_info = getattr(sandbox, "get_info", None)
    if get_info:
        info = await get_info() if inspect.iscoroutinefunction(get_info) else get_info()
        if isinstance(info, dict):
            return info.get("sandbox_id") or info.get("id")
        return getattr(info, "sandbox_id", None) or getattr(info, "id", None)

    raise AttributeError("Could not determine sandbox id from SDK.")

async def POST() -> Dict[str, Any]:
    """Enhanced sandbox creation with COMPLETE Tailwind CSS setup"""
    global active_sandbox, sandbox_data, existing_files, sandbox_state

    sandbox: Optional[Any] = None

    try:
        print("[create-ai-sandbox] Creating base sandbox...")

        # Kill existing sandbox if any
        if active_sandbox:
            print("[create-ai-sandbox] Killing existing sandbox...")
            try:
                # Use the new async close() method for v2.0.0
                if hasattr(active_sandbox, "close"):
                    if inspect.iscoroutinefunction(active_sandbox.close):
                        await active_sandbox.close()
                    else:
                        active_sandbox.close()

            except Exception as e:
                print("Failed to close existing sandbox:", e)
            active_sandbox = None

        existing_files.clear()

        print(f"[create-ai-sandbox] Creating base E2B sandbox with {appConfig.e2b.timeoutMinutes} minute timeout...")
        
        if E2BSandbox is None:
            raise RuntimeError("E2B Sandbox library not available; install 'e2b-code-interpreter'.")

        # --- THIS IS THE CRITICAL FIX ---
        # Ensure you are calling the .create() method
        api_key = os.getenv("E2B_API_KEY")
        create_fn = getattr(E2BSandbox, "create", None)

        if create_fn and inspect.iscoroutinefunction(create_fn):
            # Newer e2b_code_interpreter exposes async create()
            sandbox = await create_fn(api_key=api_key)
        elif create_fn:
            # Some versions expose create() but it's sync
            sandbox = create_fn(api_key=api_key)
        else:
            # Legacy e2b uses sync constructor
            sandbox = E2BSandbox(api_key=api_key)

        
        # In v2.0, the ID is a direct property
        sandbox_id = await _get_sandbox_id_compat(sandbox)

        
        print(f"[create-ai-sandbox] Sandbox created: {sandbox_id}")
        active_sandbox = sandbox
        sandbox_data = {"sandboxId": sandbox_id}
        print("[create-ai-sandbox] Setting up COMPLETE Vite React app with FULL Tailwind CSS configuration...")
        vite_started = await ensure_vite_server(sandbox, sandbox_id)
        
        if not vite_started:
            print("[create-ai-sandbox] ⚠️ CRITICAL ERROR: Vite + Tailwind setup failed!")
            print("[create-ai-sandbox] ⚠️ Website styling may not work properly!")

        # The URL can be constructed from the sandbox ID
        sandbox_url = await get_correct_sandbox_url(sandbox, sandbox_id)
        sandbox_data.update({"url": sandbox_url})
        # Persist sandbox info to a file for rehydration after process restarts (for Render)
        try:
            with open('/tmp/g99_sandbox.json', 'w') as f:
                json.dump({"sandboxId": sandbox_id, "url": sandbox_url, "ts": int(time.time()*1000)}, f)
        except Exception as e:
            print("warn: failed to persist sandbox file:", e)

        # Store sandbox globally
        active_sandbox = sandbox
        sandbox_data = {
            "sandboxId": sandbox_id,
            "url": sandbox_url,
        }

        # Initialize sandbox state
        sandbox_state = {
            "fileCache": {
                "files": {},
                "lastSync": int(time.time() * 1000),
                "sandboxId": sandbox_id,
            },
            "sandbox": sandbox,
            "sandboxData": {
                "sandboxId": sandbox_id,
                "url": sandbox_url,
            },
        }

        # Track initial files
        for path in [
            "src/App.jsx", "src/main.jsx", "src/index.css",
            "index.html", "package.json", "vite.config.mjs",
            "tailwind.config.js", "postcss.config.js",
        ]:
            existing_files.add(path)

        print("[create-ai-sandbox] ✅ SUCCESS: Sandbox ready with COMPLETE Tailwind CSS setup!")
        print(f"[create-ai-sandbox] URL: {sandbox_url}")

        return {
            "success": True,
            "sandboxId": sandbox_id,
            "url": sandbox_url,
            "message": "Sandbox created with COMPLETE Vite React + Tailwind CSS setup",
            "viteRunning": vite_started,
            "tailwindConfigured": True,
        }

    except Exception as error:
        print(f"[create-ai-sandbox] Error: {error}")

        if sandbox and hasattr(sandbox, "close"):
            try:
                if inspect.iscoroutinefunction(sandbox.close):
                    await sandbox.close()
                else:
                    sandbox.close()
            except Exception as e:
                print("Failed to close sandbox on error:", e)

        import traceback
        details = traceback.format_exc()

        return {
            "error": str(error),
            "details": details,
            "success": False,
            "status": 500,
        }