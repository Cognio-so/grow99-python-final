from typing import Any, Dict, Optional
import inspect

# Use shared sandbox state if available
try:
    from sandbox_state import active_sandbox  # type: ignore
except Exception:
    active_sandbox: Optional[Any] = None


async def _ensure_awaited(x):
    """Await if needed, else return as-is."""
    return (await x) if inspect.isawaitable(x) else x


async def _run_in_sandbox(sb: Any, code: str) -> Dict[str, Any]:
    """Execute code in E2B sandbox with compatibility across SDKs."""
    exec_method = None
    for name in ("run_code", "runCode", "execute", "exec", "run"):
        if hasattr(sb, name):
            exec_method = getattr(sb, name)
            break
    if exec_method is None:
        raise RuntimeError("Sandbox has no compatible code execution method")

    res = exec_method(code)
    res = await _ensure_awaited(res)

    for fin in ("wait", "result", "join", "done"):
        if hasattr(res, fin):
            try:
                maybe = getattr(res, fin)()
                if inspect.isawaitable(maybe):
                    await maybe
            except TypeError:
                pass
            except Exception:
                pass

    return res


def _extract_output_safe(result: Any) -> str:
    """Safe output extraction that handles E2B Logs objects and dicts."""
    try:
        if isinstance(result, dict):
            if "output" in result:
                output = result["output"]
                return str(output) if output is not None else ""
        if hasattr(result, "logs"):
            logs_obj = result.logs
            if hasattr(logs_obj, "stdout"):
                stdout_data = logs_obj.stdout
                if isinstance(stdout_data, list):
                    return "".join(str(x) for x in stdout_data)
                elif stdout_data is not None:
                    return str(stdout_data)
        if hasattr(result, "output"):
            output_data = result.output
            return str(output_data) if output_data is not None else ""
        return str(result) if result is not None else ""
    except Exception:
        return ""


async def POST() -> dict:
    """
    Restart Vite in the sandbox with:
    - Vite 6
    - vite.config.mjs that allow-lists *.e2b.app/.dev and correct HMR host
    - Tailwind/PostCSS configs ensured
    - dependency install with legacy peer deps and extended timeout
    """
    try:
        if active_sandbox is None:
            return {"success": False, "error": "No active sandbox"}

        print("[restart-vite] Forcing Vite restart with external access configuration...")

        embedded_code = r'''
import subprocess, os, signal, time, threading, json, socket, sys

APP_DIR = '/home/user/app'
PORT = 5173

def sh(cmd: list[str], **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)

def comprehensive_cleanup():
    print("🧹 Cleanup...")
    patterns = [
        ['pkill','-f','vite'],
        ['pkill','-f','node.*vite'],
        ['pkill','-f','npm.*dev'],
        ['pkill','-9','-f','vite'],
    ]
    for p in patterns:
        try:
            r = sh(p, timeout=5)
            if r.returncode == 0 and (r.stdout.strip() or r.stderr.strip()):
                print(f"   ✓ {' '.join(p)} -> {r.stdout.strip() or r.stderr.strip()}")
        except Exception:
            pass
    try:
        with open('/tmp/vite-process.pid','r') as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGKILL)
        print(f"   ✓ Killed stored PID: {pid}")
    except Exception:
        pass
    try:
        r = sh(['lsof','-ti:%d' % PORT])
        if r.stdout.strip():
            for pid in [p for p in r.stdout.strip().split('\n') if p]:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    print(f"   ✓ Killed PID {pid} using port {PORT}")
                except Exception:
                    pass
    except Exception:
        pass
    time.sleep(2)
    print("   ✅ Cleanup complete")

def ensure_app_dir():
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(os.path.join(APP_DIR,'src'), exist_ok=True)

def write_package_json():
    print("⚙️  Updating package.json...")
    os.chdir(APP_DIR)
    pkg_path = os.path.join(APP_DIR, 'package.json')
    pkg = {
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
    try:
        if os.path.exists(pkg_path):
            with open(pkg_path,'r') as f:
                existing = json.load(f)
        else:
            existing = {}
        existing.setdefault('name', pkg['name'])
        existing.setdefault('version', pkg['version'])
        existing.setdefault('type', 'module')
        existing.setdefault('dependencies', {}).update(pkg['dependencies'])
        dev = existing.setdefault('devDependencies', {})
        dev['vite'] = pkg['devDependencies']['vite']
        dev['@vitejs/plugin-react'] = pkg['devDependencies']['@vitejs/plugin-react']
        for k in ('tailwindcss','postcss','autoprefixer'):
            dev.setdefault(k, pkg['devDependencies'][k])
        scr = existing.setdefault('scripts', {})
        scr['dev'] = pkg['scripts']['dev']
        scr['build'] = pkg['scripts']['build']
        scr['preview'] = pkg['scripts']['preview']
        with open(pkg_path,'w') as f:
            json.dump(existing, f, indent=2)
        print("   ✓ package.json ready (Vite 6 + --config vite.config.mjs)")
        return True
    except Exception as e:
        print(f"   ❌ Could not write package.json: {e}")
        return False

def write_vite_config():
    print("⚙️ Writing vite.config.mjs...")
    config = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const port = 5173
const id = process.env.E2B_SANDBOX_ID || ''

// Build the allowed hosts list
const allowedHosts = [
  'localhost',
  '127.0.0.1',
  '0.0.0.0'
]

// Add E2B specific hosts
if (id) {
  allowedHosts.push(`${port}-${id}.e2b.app`)
  allowedHosts.push(`${port}-${id}.e2b.dev`) 
  allowedHosts.push(`${id}.e2b.app`)
  allowedHosts.push(`${id}.e2b.dev`)
}

// Add wildcard patterns
allowedHosts.push('.e2b.app')
allowedHosts.push('.e2b.dev')

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port,
    strictPort: true,
    allowedHosts: allowedHosts,  // Use explicit array instead of 'all'
    hmr: {
      port: false
    },
    watch: { 
      usePolling: true, 
      interval: 1000,
      ignored: ['**/node_modules/**', '**/.git/**']
    }
  },
  preview: {
    host: '0.0.0.0',
    port,
    strictPort: true,
    allowedHosts: allowedHosts  // Same list for preview
  },
  define: { 
    'process.env': {},
    global: 'globalThis'
  },
  optimizeDeps: {
    include: ['react', 'react-dom']
  }
})
"""
    try:
        with open(os.path.join(APP_DIR,'vite.config.mjs'),'w') as f:
            f.write(config)
        sh(['touch', os.path.join(APP_DIR,'vite.config.mjs')])
        print("   ✓ vite.config.mjs written")
        return True
    except Exception as e:
        print(f"   ❌ Could not write vite.config.mjs: {e}")
        return False

def write_tailwind_postcss():
    try:
        with open(os.path.join(APP_DIR,'tailwind.config.cjs'),'w') as f:
            f.write("""module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} },
  plugins: []
}""")
        with open(os.path.join(APP_DIR,'postcss.config.cjs'),'w') as f:
            f.write("""module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {}
  }
}""")
        # Ensure index.css has Tailwind directives (overwrite is fine)
        cssp = os.path.join(APP_DIR,'src','index.css')
        os.makedirs(os.path.dirname(cssp), exist_ok=True)
        with open(cssp,'w') as f:
            f.write("""@tailwind base;
@tailwind components;
@tailwind utilities;

:root { color-scheme: light; }
body { @apply bg-gray-50 text-gray-900 antialiased; }
a { @apply text-blue-600 underline hover:text-blue-700; }
""")
        print("   ✓ tailwind.config.cjs, postcss.config.cjs, and src/index.css written")
        return True
    except Exception as e:
        print(f"   ❌ Could not write Tailwind/PostCSS configs: {e}")
        return False

def install_dependencies():
    print("📦 Installing dependencies (legacy peer deps)...")
    os.chdir(APP_DIR)
    r = sh(['npm','install','--legacy-peer-deps'])
    if r.returncode == 0:
        print("   ✓ npm install ok")
        v = sh(['npx','vite','--version'])
        print(f"   vite version: {(v.stdout or v.stderr).strip()}")
        return True
    print("   ⚠️ npm install issues")
    print(r.stderr or r.stdout)
    return False

def start_vite_server():
    print("🚀 Starting Vite dev server...")
    env = os.environ.copy()
    env.update({
        'HOST': '0.0.0.0',
        'PORT': str(PORT),
        'VITE_HOST': '0.0.0.0',
        'VITE_PORT': str(PORT),
        'NODE_ENV': 'development',
        'FORCE_COLOR': '0',
        'CI': 'false',
        '__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS': '.e2b.app,.e2b.dev,e2b.local'
    })
    def monitor(pipe, tag):
        while True:
            line = pipe.readline()
            if not line:
                break
            print(f"[{tag}] {line.rstrip()}")
    try:
        proc = subprocess.Popen(
            ['npm','run','dev'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=APP_DIR,
            env=env,
            preexec_fn=os.setsid if hasattr(os, 'setsid') else None
        )
        print(f"   ✓ PID: {proc.pid}")
        with open('/tmp/vite-process.pid','w') as f:
            f.write(str(proc.pid))
        threading.Thread(target=monitor, args=(proc.stdout,'STDOUT'), daemon=True).start()
        threading.Thread(target=monitor, args=(proc.stderr,'STDERR'), daemon=True).start()
        return proc
    except Exception as e:
        print(f"   ❌ Failed to start Vite: {e}")
        return None

def test_connectivity():
    print("🔍 Connectivity checks...")
    results = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        rc = s.connect_ex(('localhost', PORT))
        s.close()
        ok = (rc == 0)
        print(f"   localhost:{PORT} = {'✅' if ok else '❌'}")
        results.append(('tcp', ok))
    except Exception:
        print(f"   localhost:{PORT} = ❌")
        results.append(('tcp', False))
    try:
        import requests
        r = requests.get(f'http://localhost:{PORT}', timeout=3)
        ok = (r.status_code < 500)
        print(f"   HTTP {r.status_code} = {'✅' if ok else '❌'}")
        results.append(('http', ok))
    except Exception as e:
        print(f"   HTTP error = ❌ ({e})")
        results.append(('http', False))
    return results

# ---- Sequence ----
os.makedirs(APP_DIR, exist_ok=True)
os.makedirs(os.path.join(APP_DIR,'src'), exist_ok=True)

comprehensive_cleanup()
write_package_json()
write_vite_config()
write_tailwind_postcss()
install_dependencies()

proc = start_vite_server()
if not proc:
    print("RESTART_STATUS: FAILED")
    print("EXTERNAL_ACCESS: FALSE")
    sys.exit(0)

print("⏳ Waiting for server startup...")
startup_ok = False
for i in range(20):
    time.sleep(1)
    if proc.poll() is not None:
        print(f"   ❌ Process exited early with code: {proc.poll()}")
        break
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        rc = s.connect_ex(('localhost', PORT))
        s.close()
        if rc == 0:
            startup_ok = True
            print(f"   ✅ Port open after {i+1}s")
            break
    except Exception:
        pass

results = test_connectivity()
ok_count = sum(1 for _, ok in results if ok)

if startup_ok and ok_count >= 1:
    print("🎉 Vite restart successful")
    print("RESTART_STATUS: SUCCESS")
    print("EXTERNAL_ACCESS: TRUE")
elif startup_ok:
    print("⚠️ Vite restarted; external access uncertain")
    print("RESTART_STATUS: PARTIAL")
    print("EXTERNAL_ACCESS: UNKNOWN")
else:
    print("❌ Vite restart failed")
    print("RESTART_STATUS: FAILED")
    print("EXTERNAL_ACCESS: FALSE")
'''.lstrip("\n")

        result = await _run_in_sandbox(active_sandbox, embedded_code)
        output = _extract_output_safe(result)

        if "RESTART_STATUS: SUCCESS" in output:
            success = True
            message = "Vite restarted successfully with external access"
            external_access = True
        elif "RESTART_STATUS: PARTIAL" in output:
            success = True
            message = "Vite restarted but external access needs verification"
            external_access = False
        else:
            success = False
            message = "Vite restart failed"
            external_access = False

        return {
            "success": success,
            "message": message,
            "output": output,
            "external_access_configured": True,
            "external_access_verified": external_access,
            "restart_status": "SUCCESS" if success else "FAILED"
        }

    except Exception as error:
        print(f"[restart-vite] Error: {error}")
        return {
            "success": False,
            "error": str(error),
            "external_access_configured": False,
            "restart_status": "ERROR"
        }