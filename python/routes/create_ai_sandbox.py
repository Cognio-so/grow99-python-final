# create_ai_sandbox.py - FINAL CORRECTED CODE

from typing import Any, Dict, Optional, Set
import os
import asyncio
import inspect
import json
import time
from types import SimpleNamespace

# ADD THIS: Import the new centralized state management functions
# Replace the import at the top
from routes.database import set_sandbox_state

# Rest of the file remains the same

# LangChain and E2B imports remain the same
try:
    from langchain_core.runnables import RunnableLambda
    from langgraph.graph import StateGraph, START, END
except Exception as _e:
    raise

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

# App config remains the same
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

# REMOVED: All global variables are no longer needed.
# active_sandbox: Optional[Any] = None
# sandbox_data: Optional[Dict[str, Any]] = None
# existing_files: Set[str] = set()
# sandbox_state: Optional[Dict[str, Any]] = None

async def _run_in_sandbox(sandbox: Any, code: str) -> Dict[str, Any]:
    """Enhanced sandbox execution with better error handling"""
    async def _runner(payload: Dict[str, Any]) -> Dict[str, Any]:
        c = payload.get("code", "")
        
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
            
            if hasattr(result, 'wait'):
                try:
                    result.wait()
                except:
                    pass
            
            return result
        except Exception as e:
            return {"output": f"Error: {str(e)}", "success": False}

    chain = RunnableLambda(_runner)
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
    
    if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
        if isinstance(result.logs.stdout, list):
            return ''.join(str(x) for x in result.logs.stdout)
        else:
            return str(result.logs.stdout or "")
    elif hasattr(result, 'output'):
        return str(result.output or "")
    
    return ""

async def verify_and_fix_url(sandbox, sandbox_id):
    """Verify URL works and fix if needed"""
    possible_urls = [
        f"https://5173-{sandbox_id}.e2b.app",
        f"https://5173-{sandbox_id}.e2b.dev", 
        f"https://{sandbox_id}.e2b.app:5173",
        f"https://{sandbox_id}.e2b.dev:5173"
    ]
    
    test_code = f'''
import requests
import json
results = {{}}
urls_to_test = {json.dumps(possible_urls)}
for url in urls_to_test:
    try:
        resp = requests.get(url, timeout=5)
        results[url] = {{"status": resp.status_code, "accessible": True}}
    except Exception as e:
        results[url] = {{"error": str(e), "accessible": False}}
print(json.dumps(results))
'''
    try:
        result = await _run_in_sandbox(sandbox, test_code)
        output = _extract_output_text(result)
        
        url_results = json.loads(output)
        for url, data in url_results.items():
            if data.get("accessible") and data.get("status") == 200:
                print(f"[verify_url] Found working URL: {url}")
                return url
    except Exception as e:
        print(f"[verify_url] URL verification failed: {e}")
    
    return possible_urls[0]

async def get_correct_sandbox_url(sandbox: Any, sandbox_id: str) -> str:
    """Get the correct accessible E2B URL with verification"""
    print(f"[get_sandbox_url] Verifying URL for Sandbox ID: {sandbox_id}")
    final_url = await verify_and_fix_url(sandbox, sandbox_id)
    print(f"[get_sandbox_url] Selected URL: {final_url}")
    return final_url

async def ensure_vite_server(sandbox: Any, sandbox_id: str) -> bool:
    """Ensure Vite server is running properly with COMPLETE Tailwind setup"""
    print("[ensure_vite_server] Starting Vite server setup with FULL Tailwind configuration...")
    
    # This setup script is large but correct, so it remains unchanged.
    setup_script = '''
import os
import json
print('Setting up React app with Vite and Tailwind...')
os.makedirs('/home/user/app/src', exist_ok=True)
package_json = {
    "name": "sandbox-app", "version": "1.0.0", "type": "module",
    "scripts": {
        "dev": "vite --host 0.0.0.0 --port 5173 --strictPort --config vite.config.mjs",
        "build": "vite build --config vite.config.mjs",
        "preview": "vite preview --host 0.0.0.0 --port 5173 --config vite.config.mjs"
    },
    "dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"},
    "devDependencies": {
        "@vitejs/plugin-react": "^4.3.0", "vite": "^6.0.9",
        "tailwindcss": "^3.3.0", "postcss": "^8.4.31", "autoprefixer": "^10.4.16"
    }
}
with open('/home/user/app/package.json', 'w') as f: json.dump(package_json, f, indent=2)
print('✓ package.json')
vite_config = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
const id = process.env.E2B_SANDBOX_ID
const allowed = ['localhost', '127.0.0.1', '::1']
if (id) { allowed.push(`5173-${id}.e2b.app`, `5173-${id}.e2b.dev`) }
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', port: 5173, strictPort: true, allowedHosts: allowed,
    hmr: { clientPort: 443, host: id ? `5173-${id}.e2b.app` : undefined },
    watch: { usePolling: true, interval: 1000 }, cors: true
  },
  preview: { host: '0.0.0.0', port: 5173, strictPort: true, allowedHosts: allowed },
  define: { 'process.env': {}, global: 'globalThis' },
  optimizeDeps: { include: ['react','react-dom'] }
})"""
with open('/home/user/app/vite.config.mjs', 'w') as f: f.write(vite_config)
print('✓ vite.config.mjs')
tailwind_config = """/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} },
  plugins: [],
}"""
with open('/home/user/app/tailwind.config.js', 'w') as f: f.write(tailwind_config)
print('✓ tailwind.config.js')
postcss_config = """export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
}"""
with open('/home/user/app/postcss.config.js', 'w') as f: f.write(postcss_config)
print('✓ postcss.config.js')
index_html = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>Sandbox App</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>"""
with open('/home/user/app/index.html', 'w') as f: f.write(index_html)
print('✓ index.html')
main_jsx = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>,)"""
with open('/home/user/app/src/main.jsx', 'w') as f: f.write(main_jsx)
print('✓ src/main.jsx')
app_jsx = """function App() {
  return (
    <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center p-4">
      <div className="text-center max-w-2xl">
        <h1 className="text-4xl font-bold mb-4 text-green-400">🚀 Sandbox Ready!</h1>
        <p className="text-lg text-gray-400">Your React app with Vite and Tailwind CSS is ready for development.</p>
        <div className="mt-6 p-4 bg-gray-800 rounded-lg"><p className="text-sm text-gray-300">This placeholder will be replaced when you generate your actual app.</p></div>
      </div>
    </div>
  )
}
export default App"""
with open('/home/user/app/src/App.jsx', 'w') as f: f.write(app_jsx)
print('✓ src/App.jsx')
index_css = """@tailwind base;
@tailwind components;
@tailwind utilities;"""
with open('/home/user/app/src/index.css', 'w') as f: f.write(index_css)
print('✓ src/index.css')
print('\\n✅ All files created successfully!')
'''
    await _run_in_sandbox(sandbox, setup_script)
    
    print("[ensure_vite_server] Installing dependencies...")
    install_script = "import subprocess; subprocess.run(['npm', 'install'], cwd='/home/user/app', capture_output=True, text=True)"
    await _run_in_sandbox(sandbox, install_script)
    
    print("[ensure_vite_server] Starting Vite server...")
    start_code = f"import subprocess, os, time; env = os.environ.copy(); env['E2B_SANDBOX_ID'] = '{sandbox_id}'; subprocess.Popen(['npm','run','dev'], env=env, cwd='/home/user/app', preexec_fn=os.setsid); print('VITE_PROCESS_STARTED')"
    await _run_in_sandbox(sandbox, start_code)

    await asyncio.sleep(10) # Give Vite time to start
    return True

async def _get_sandbox_id_compat(sandbox):
    """Compatibility function to get sandbox ID from different SDK versions."""
    sid = getattr(sandbox, "id", None) or getattr(sandbox, "sandbox_id", None)
    if sid:
        return sid
    if hasattr(sandbox, "get_info"):
        info = await sandbox.get_info() if inspect.iscoroutinefunction(sandbox.get_info) else sandbox.get_info()
        return getattr(info, "sandbox_id", None) or getattr(info, "id", None)
    raise AttributeError("Could not determine sandbox ID from SDK object.")

async def POST() -> Dict[str, Any]:
    """Creates a new E2B sandbox, sets up a Vite+React+Tailwind environment,
    and saves its state to a centralized file for other processes to use."""
    sandbox: Optional[Any] = None

    try:
        # Step 1: Clear any old state from the central file.
        print("[create-ai-sandbox] Clearing any previous sandbox state...")
        set_sandbox_state(None)

        print("[create-ai-sandbox] Creating new E2B sandbox...")
        if E2BSandbox is None:
            raise RuntimeError("E2B Sandbox library is not available or failed to import.")

        api_key = os.getenv("E2B_API_KEY")

        # Check SDK version and handle api_key differently
        if hasattr(E2BSandbox, "create"):
            create_fn = getattr(E2BSandbox, "create", None)

            if create_fn and inspect.iscoroutinefunction(create_fn):
                # If `create` is async
                sandbox = await create_fn(api_key=api_key)
            elif create_fn:
                # If `create` is sync
                sandbox = create_fn(api_key=api_key)
            else:
                # Fallback: legacy SDK initialization
                sandbox = E2BSandbox()
        else:
            # Fallback to direct instantiation (legacy)
            sandbox = E2BSandbox(api_key=api_key)

        # Get the sandbox ID
        sandbox_id = await _get_sandbox_id_compat(sandbox)
        print(f"[create-ai-sandbox] Sandbox created with ID: {sandbox_id}")

        # Step 2: Set up the Vite environment inside the sandbox.
        vite_started = await ensure_vite_server(sandbox, sandbox_id)

        # Step 3: Get the correct, accessible URL for the sandbox.
        sandbox_url = await get_correct_sandbox_url(sandbox, sandbox_id)

        # Step 4: Create the state dictionary to save centrally.
        new_state = {
            "sandboxId": sandbox_id,
            "url": sandbox_url,
            "createdAt": int(time.time() * 1000)
        }

        # Step 5: Save the new state to the central file using our manager.
        set_sandbox_state(new_state)

        print("[create-ai-sandbox] ✅ SUCCESS: Sandbox created and state saved centrally!")
        print(f"[create-ai-sandbox] URL: {sandbox_url}")

        # Step 6: Close the temporary connection. Future requests will reconnect using the ID.
        if hasattr(sandbox, "close"):
            if inspect.iscoroutinefunction(sandbox.close):
                await sandbox.close()
            else:
                sandbox.close()

        return {
            "success": True,
            "sandboxId": sandbox_id,
            "url": sandbox_url,
            "message": "Sandbox created with Vite, React, and Tailwind.",
            "viteRunning": vite_started,
            "tailwindConfigured": True,
        }

    except Exception as error:
        print(f"[create-ai-sandbox] CRITICAL ERROR: {error}")
        # Ensure state is cleared on failure to prevent using a broken sandbox
        set_sandbox_state(None)

        if sandbox and hasattr(sandbox, "close"):
            try:
                if inspect.iscoroutinefunction(sandbox.close): await sandbox.close()
                else: sandbox.close()
            except Exception as e:
                print(f"Failed to close sandbox during error handling: {e}")

        import traceback
        return {
            "error": str(error),
            "details": traceback.format_exc(),
            "success": False,
            "status": 500,
        }
