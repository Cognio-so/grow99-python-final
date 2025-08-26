# apply_ai_code_stream.py - FIXED with robust file parsing matching generate_ai_stream.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os
import re
import sys
import json
import inspect
import asyncio
import unicodedata
from types import SimpleNamespace
from pathlib import Path
# from routes.state_manager import save_state/
# Responses for main_app to return directly
try:
    from fastapi.responses import StreamingResponse, JSONResponse  # type: ignore
except Exception:  # pragma: no cover
    StreamingResponse = None  # type: ignore
    JSONResponse = None  # type: ignore

# LangChain / LangGraph
try:
    from langchain_core.runnables import RunnableLambda
    from langgraph.graph import StateGraph, START, END
except Exception as _e:  # pragma: no cover
    raise

# E2B Sandbox (python SDK)
try:
    from e2b import Sandbox as E2BSandbox  # type: ignore
except Exception:
    try:
        from e2b_code_interpreter import Sandbox as E2BSandbox  # type: ignore
    except Exception:
        E2BSandbox = None

# --------------------------
# Globals (synced by main_app)
# --------------------------
active_sandbox: Optional[Any] = None
sandbox_data: Optional[Dict[str, Any]] = None
existing_files: Optional[set] = set()
sandbox_state: Optional[Dict[str, Any]] = None
conversation_state: Optional[Dict[str, Any]] = None


# --------------------------
# UTF-8 Sanitization Function
# --------------------------
def sanitize_content_for_utf8(content: str) -> str:
    """Enhanced sanitization for JSX content"""
    if not isinstance(content, str):
        return str(content)
    
    # Fix encoding issues
    content = content.encode('utf-8', errors='replace').decode('utf-8')
    
    # Fix smart quotes (main cause of JSX syntax errors)
    replacements = {
        '"': '"',    # Left double quotation mark
        '"': '"',    # Right double quotation mark  
        ''': "'",    # Left single quotation mark
        ''': "'",    # Right single quotation mark
        '–': '-',    # En dash
        '—': '--',   # Em dash
        '…': '...',  # Horizontal ellipsis
        ' ': ' ',    # Non-breaking space
    }
    
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    return content
def sanitize_and_validate_jsx(content: str, file_path: str) -> str:
    """Comprehensive JSX sanitization and validation"""
    
    # Step 1: Fix encoding issues
    content = content.encode('utf-8', errors='replace').decode('utf-8')
    
    # Step 2: Fix smart quotes - this is the main issue
    replacements = {
        '"': '"',    # Left double quotation mark
        '"': '"',    # Right double quotation mark  
        ''': "'",    # Left single quotation mark
        ''': "'",    # Right single quotation mark
        '–': '-',    # En dash
        '—': '--',   # Em dash
        '…': '...',  # Horizontal ellipsis
        ' ': ' ',    # Non-breaking space
    }
    
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    # Step 3: JSX-specific fixes
    if file_path.endswith('.jsx'):
        # Ensure React import
        if 'import React' not in content and ('function ' in content or 'const ' in content):
            if content.strip().startswith('import'):
                # Add after existing imports
                lines = content.split('\n')
                import_end = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith('import'):
                        import_end = i + 1
                    elif line.strip() and not line.strip().startswith('import'):
                        break
                lines.insert(import_end, "import React from 'react'")
                content = '\n'.join(lines)
            else:
                content = "import React from 'react'\n\n" + content
        
        # Ensure export default
        if 'export default' not in content:
            # Find function name
            func_match = re.search(r'(?:function|const)\s+(\w+)', content)
            if func_match:
                func_name = func_match.group(1)
                if not content.strip().endswith(f'export default {func_name}'):
                    content = content.rstrip() + f'\n\nexport default {func_name}'
        
        # Fix common JSX syntax issues
        # Fix className quotes
        content = re.sub(r'className=\{([^}]+)\}', r'className={\1}', content)
        
        # Remove any remaining problematic characters
        content = re.sub(r'[^\x20-\x7E\n\t\r]', '', content)
    
    return content


# --------------------------
# Improved Sandbox Interaction
# --------------------------
# Add this to your apply_ai_code_stream.py to prevent file pollution

async def clean_components_directory_before_generation(sandbox):
    """Clean components directory before creating new components to prevent pollution"""
    
    cleanup_code = """
import os
import shutil
import json

components_dir = "/home/user/app/src/components"
cleaned_files = []

print("=== CLEANING COMPONENTS DIRECTORY ===")

if os.path.exists(components_dir):
    try:
        # List all files before cleanup
        existing_files = []
        for root, dirs, files in os.walk(components_dir):
            for file in files:
                if file.endswith(('.jsx', '.js', '.tsx', '.ts')):
                    file_path = os.path.join(root, file)
                    existing_files.append(os.path.relpath(file_path, "/home/user/app"))
        
        if existing_files:
            print(f"Found {len(existing_files)} existing component files:")
            for f in existing_files:
                print(f"  - {f}")
            
            # Remove the entire components directory
            shutil.rmtree(components_dir)
            cleaned_files = existing_files
            print("✅ Removed all existing components")
        else:
            print("✅ Components directory was already clean")
    except Exception as e:
        print(f"❌ Error cleaning components: {e}")
else:
    print("✅ Components directory doesn't exist (clean start)")

# Recreate clean components directory
os.makedirs(components_dir, exist_ok=True)
print("✅ Created fresh components directory")

# Return results
result = {
    "cleaned": True,
    "filesRemoved": len(cleaned_files),
    "removedFiles": cleaned_files
}

print(f"CLEANUP_RESULT: {json.dumps(result)}")
"""
    
    try:
        from routes.apply_ai_code_stream import _run_in_sandbox
        result = await _run_in_sandbox(sandbox, cleanup_code)
        
        if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
            output = ''.join(result.logs.stdout) if isinstance(result.logs.stdout, list) else str(result.logs.stdout or "")
        else:
            output = str(result)
        
        print(f"[clean_components] {output}")
        
        # Parse cleanup result
        import json
        import re
        result_match = re.search(r'CLEANUP_RESULT: ({.*})', output)
        if result_match:
            try:
                cleanup_result = json.loads(result_match.group(1))
                return cleanup_result
            except:
                pass
        
        return {"cleaned": "CLEANUP_RESULT" in output, "filesRemoved": 0, "removedFiles": []}
        
    except Exception as e:
        print(f"[clean_components] Error: {e}")
        return {"cleaned": False, "error": str(e)}

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
                # E2B Execution object - wait for completion
                try:
                    result.wait()
                except:
                    pass
            
            return {"output": "", "success": True, "result": result}
                
        except Exception as e:
            return {"output": f"Error: {str(e)}", "success": False, "error": str(e)}

    chain = RunnableLambda(_runner)

    def _compile_graph():
        g = StateGraph(dict)

        async def exec_node(state: Dict[str, Any]) -> Dict[str, Any]:
            return await chain.ainvoke(state)

        g.add_node("exec", exec_node)
        g.add_edge(START, "exec")
        g.add_edge("exec", END)
        return g.compile()

    if not hasattr(_run_in_sandbox, "_graph"):
        _run_in_sandbox._graph = _compile_graph()

    graph = _run_in_sandbox._graph
    return await graph.ainvoke({"code": code})


def _extract_output_text(result: Any) -> str:
    """Enhanced output extraction with better error handling"""
    if isinstance(result, dict):
        # Try different output field names
        for field in ['output', 'stdout', 'result']:
            out = result.get(field)
            if isinstance(out, str) and out.strip():
                return out
        
        # Try logs structure
        logs = result.get("logs")
        if isinstance(logs, dict):
            stdout = logs.get("stdout")
            if isinstance(stdout, list):
                return "".join(str(x) for x in stdout)
            elif isinstance(stdout, str):
                return stdout
        
        # Handle nested result object
        nested_result = result.get("result")
        if nested_result:
            if hasattr(nested_result, "logs") and hasattr(nested_result.logs, "stdout"):
                if isinstance(nested_result.logs.stdout, list):
                    return "".join(str(x) for x in nested_result.logs.stdout)
                else:
                    return str(nested_result.logs.stdout or "")
            elif hasattr(nested_result, "output"):
                return str(nested_result.output or "")
    
    return str(result) if result else ""

async def debug_component_content(sandbox, file_paths):
    """Debug function to check actual component content"""
    debug_code = f"""
import os
import json

files_content = {{}}
file_paths = {json.dumps(file_paths)}

for file_path in file_paths:
    full_path = f"/home/user/app/{{file_path}}"
    if os.path.exists(full_path):
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                files_content[file_path] = {{
                    "content": content,
                    "length": len(content),
                    "first_100_chars": content[:100],
                    "has_import_react": "import React" in content,
                    "has_export_default": "export default" in content,
                    "has_smart_quotes": any(char in content for char in ['"', '"', ''', ''']),
                }}
        except Exception as e:
            files_content[file_path] = {{"error": str(e)}}
    else:
        files_content[file_path] = {{"error": "File not found"}}

print("=== COMPONENT DEBUG INFO ===")
for file_path, info in files_content.items():
    print(f"\\n--- {{file_path}} ---")
    if "error" in info:
        print(f"ERROR: {{info['error']}}")
    else:
        print(f"Length: {{info['length']}} chars")
        print(f"Has React import: {{info['has_import_react']}}")
        print(f"Has export default: {{info['has_export_default']}}")
        print(f"Has smart quotes: {{info['has_smart_quotes']}}")
        print(f"First 100 chars: {{repr(info['first_100_chars'])}}")
print("=== END DEBUG INFO ===")
"""
    
    try:
        result = await _run_in_sandbox(sandbox, debug_code)
        output = _extract_output_text(result)
        print(f"[debug_component_content] {output}")
        return output
    except Exception as e:
        print(f"[debug_component_content] Error: {e}")
        return ""
# --------------------------
# Force Vite Reload Function
# --------------------------
async def force_vite_reload_after_changes(sandbox, files_changed):
    """FIXED: More reliable Vite restart"""
    
    restart_code = f"""
import subprocess
import time
import socket

print("=== RESTARTING VITE FOR FILE CHANGES ===")

# Kill existing Vite processes
subprocess.run(['pkill', '-f', 'vite'], capture_output=True)
subprocess.run(['pkill', '-f', 'node.*vite'], capture_output=True)
time.sleep(3)

# Clear Vite cache
subprocess.run(['rm', '-rf', 'node_modules/.vite'], capture_output=True)
subprocess.run(['rm', '-rf', '.vite'], capture_output=True)

# Start Vite with better error handling
import os
os.chdir('/home/user/app')

try:
    process = subprocess.Popen(
        ['npm', 'run', 'dev'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid if hasattr(os, 'setsid') else None
    )
    
    print(f"Vite started with PID: {{process.pid}}")
    
    # Wait longer for startup
    time.sleep(10)
    
    # Test if server is responding
    for attempt in range(15):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('localhost', 5173))
            sock.close()
            
            if result == 0:
                print("SUCCESS: Vite server is responding")
                break
        except:
            pass
        time.sleep(1)
    else:
        print("WARNING: Vite server may not be responding")
        
    # Check for errors in stderr
    try:
        outs, errs = process.communicate(timeout=1)
    except:
        outs, errs = "", ""
        
    if errs and "error" in errs.lower():
        print(f"VITE ERRORS: {{errs}}")
    
except Exception as e:
    print(f"FAILED to start Vite: {{e}}")

print("=== RESTART COMPLETE ===")
"""

    try:
        result = await _run_in_sandbox(sandbox, restart_code)
        output = _extract_output_text(result)
        print(f"[force_vite_reload] {output}")
        return "SUCCESS: Vite server is responding" in output
    except Exception as e:
        print(f"[force_vite_reload] Error: {e}")
        return False
# --------------------------
# FIXED FILE PARSER - EXACT COPY FROM generate_ai_stream.py
# --------------------------
async def check_vite_errors(sandbox):
    """Check Vite server for compilation errors"""
    check_code = """
import subprocess
import time

# Check Vite process status
try:
    result = subprocess.run(['pgrep', '-f', 'vite'], capture_output=True, text=True)
    if result.stdout.strip():
        print("Vite process is running")
        
        # Try to make a request to check for errors
        try:
            import requests
            response = requests.get('http://localhost:5173', timeout=5)
            print(f"Vite response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"Vite error response: {response.text[:500]}")
        except Exception as e:
            print(f"Request to Vite failed: {e}")
    else:
        print("Vite process not running")
        
except Exception as e:
    print(f"Error checking Vite: {e}")

# Check Vite logs for errors
try:
    with open('/home/user/app/vite-error.log', 'r') as f:
        errors = f.read()
        if errors:
            print(f"Vite errors: {errors}")
except:
    print("No Vite error log found")
"""
    
    try:
        result = await _run_in_sandbox(sandbox, check_code)
        output = _extract_output_text(result)
        print(f"[check_vite_errors] {output}")
        return output
    except Exception as e:
        print(f"[check_vite_errors] Error: {e}")
        return ""
def parse_ai_response(response: str) -> Dict[str, Any]:
    """FIXED: Enhanced AI response parser with robust file detection"""
    sections: Dict[str, Any] = {
        "files": [],
        "commands": [],
        "packages": [],
        "structure": None,
        "explanation": "",
        "template": "",
    }

    print(f"[parse_ai_response] Parsing response of {len(response)} characters")

    # Function to extract packages from import statements
    def extract_packages_from_code(content: str) -> List[str]:
        packages = []
        # Match ES6 imports
        import_regex = re.compile(r'import\s+(?:(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)(?:\s*,\s*(?:\{[^}]*\}|\*\s+as\s+\w+|\w+))*\s+from\s+)?[\'"]([^\'"]+)[\'"]')
        
        for import_match in import_regex.finditer(content):
            import_path = import_match.group(1)
            # Skip relative imports and built-in React
            if (not import_path.startswith('.') and not import_path.startswith('/') and 
                import_path != 'react' and import_path != 'react-dom' and
                not import_path.startswith('@/')):
                # Extract package name (handle scoped packages like @heroicons/react)
                if import_path.startswith('@'):
                    package_name = '/'.join(import_path.split('/')[:2])
                else:
                    package_name = import_path.split('/')[0]
                
                if package_name not in packages:
                    packages.append(package_name)
                    print(f'[parse_ai_response] Package detected from imports: {package_name}')
        
        return packages

    # FIXED: Parse file sections with ROBUST detection - handle duplicates and prefer complete versions
    file_map = {}
    
    # Strategy 1: Standard XML format (preferred)
    xml_pattern = r'<file\s+path="([^"]+)">(.*?)</file>'
    xml_matches = re.findall(xml_pattern, response, re.DOTALL)

    if xml_matches:
        print(f"[parse_ai_response] Found {len(xml_matches)} XML files")
        for path, content in xml_matches:
            cleaned_content = sanitize_content_for_utf8(content.strip())
            if cleaned_content:
                file_map[path] = {"content": cleaned_content, "is_complete": True}
                print(f"[parse_ai_response] XML: {path} ({len(cleaned_content)} chars)")

    # Strategy 2: Incomplete XML (streaming or cut-off)
    if not file_map:
        incomplete_pattern = r'<file\s+path="([^"]+)">(.*?)(?=<file|$)'
        incomplete_matches = re.findall(incomplete_pattern, response, re.DOTALL)

        if incomplete_matches:
            print(f"[parse_ai_response] Found {len(incomplete_matches)} incomplete XML files")
            for path, content in incomplete_matches:
                cleaned_content = sanitize_content_for_utf8(content.replace("</file>", "").strip())
                if cleaned_content and len(cleaned_content) > 10:
                    file_map[path] = {"content": cleaned_content, "is_complete": False}
                    print(f"[parse_ai_response] Incomplete XML: {path} ({len(cleaned_content)} chars)")

    # Strategy 3: Code blocks with file paths
    if not file_map:
        code_block_patterns = [
            r'```(?:jsx|js|javascript|tsx|ts|css)\s+(?:path=["\'`])?([^\s\n"\'`]+\.(?:jsx?|tsx?|css))\s*\n(.*?)\n```',
            r'```(?:jsx|js|javascript|tsx|ts|css)\s*\n(?://\s*)?([^\s\n]+\.(?:jsx?|tsx?|css))\s*\n(.*?)\n```',
        ]
        
        for pattern in code_block_patterns:
            code_matches = re.findall(pattern, response, re.DOTALL)
            if code_matches:
                print(f"[parse_ai_response] Found {len(code_matches)} code block files")
                for path, content in code_matches:
                    # Ensure path starts with src/ if it's a component
                    if not path.startswith("src/") and (path.endswith('.jsx') or path.endswith('.tsx') or path.endswith('.js') or path.endswith('.ts')):
                        if "components/" in path:
                            path = "src/" + path
                        elif not path.startswith("/") and path != "index.css":
                            path = "src/" + path
                    elif path == "index.css":
                        path = "src/index.css"
                    
                    cleaned_content = sanitize_content_for_utf8(content.strip())
                    if cleaned_content:
                        file_map[path] = {"content": cleaned_content, "is_complete": True}
                        print(f"[parse_ai_response] Code block: {path}")
                break

    # Strategy 4: Markdown-style file headers
    if not file_map:
        markdown_pattern = r'\*\*(src/[^*\n]+)\*\*\s*```(?:jsx|js|css|json)?\s*\n(.*?)\n```'
        markdown_matches = re.findall(markdown_pattern, response, re.DOTALL)

        if markdown_matches:
            print(f"[parse_ai_response] Found {len(markdown_matches)} markdown files")
            for path, content in markdown_matches:
                file_map[path] = {"content": sanitize_content_for_utf8(content.strip()), "is_complete": True}
                print(f"[parse_ai_response] Markdown: {path}")

    # Strategy 5: React component detection and intelligent extraction
    if not file_map and ("import React" in response or "function App" in response or "export default" in response):
        print("[parse_ai_response] Detected React code, attempting intelligent extraction")

        # Try to find complete React components
        component_patterns = [
            # Full component with imports and export
            r'(import React.*?(?:export default \w+|export \{ \w+ as default \}))',
            # Just the component function/class
            r'((?:function|const) \w+.*?export default \w+)',
        ]

        extracted_components = []
        for pattern in component_patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            extracted_components.extend(matches)

        if extracted_components:
            # Create App.jsx from the largest component
            largest_component = max(extracted_components, key=len)
            file_map["src/App.jsx"] = {"content": sanitize_content_for_utf8(largest_component.strip()), "is_complete": True}
            print("[parse_ai_response] Extracted React component as App.jsx")

        # Always add a basic index.css for React apps
        if not any(path.endswith("index.css") for path in file_map):
            file_map["src/index.css"] = {
                "content": sanitize_content_for_utf8("@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\nbody {\n  margin: 0;\n  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;\n  -webkit-font-smoothing: antialiased;\n  -moz-osx-font-smoothing: grayscale;\n}"),
                "is_complete": True
            }
            print("[parse_ai_response] Added default index.css")

    # Strategy 6: Last resort - try to extract any code that looks like a file
    if not file_map:
        print("[parse_ai_response] No files found, trying last resort extraction...")
        
        # Look for any JSX/JS content
        jsx_content = re.search(r'(function \w+.*?export default \w+)', response, re.DOTALL)
        if jsx_content:
            file_map["src/App.jsx"] = {"content": sanitize_content_for_utf8(jsx_content.group(1).strip()), "is_complete": False}
            print("[parse_ai_response] Last resort: extracted JSX as App.jsx")

        # Look for CSS content
        css_content = re.search(r'(@tailwind base;.*?)', response, re.DOTALL)
        if css_content:
            file_map["src/index.css"] = {"content": sanitize_content_for_utf8(css_content.group(1).strip()), "is_complete": False}
            print("[parse_ai_response] Last resort: extracted CSS as index.css")

    # Convert file_map to sections.files
    for path, info in file_map.items():
        if not info["is_complete"]:
            print(f'[parse_ai_response] Warning: File {path} appears to be truncated')
        
        sections["files"].append({
            "path": path,
            "content": info["content"]
        })
        
        # Extract packages from file content
        file_packages = extract_packages_from_code(info["content"])
        for pkg in file_packages:
            if pkg not in sections["packages"]:
                sections["packages"].append(pkg)
                print(f'[parse_ai_response] Package detected from {path}: {pkg}')

    # Parse commands
    cmd_regex = re.compile(r'<command>(.*?)</command>')
    for match in cmd_regex.finditer(response):
        sections["commands"].append(match.group(1).strip())

    # Parse packages - support both <package> and <packages> tags
    pkg_regex = re.compile(r'<package>(.*?)</package>')
    for match in pkg_regex.finditer(response):
        pkg_name = match.group(1).strip()
        if pkg_name not in sections["packages"]:
            sections["packages"].append(pkg_name)

    # Also parse <packages> tag with multiple packages
    packages_regex = re.compile(r'<packages>([\s\S]*?)</packages>')
    packages_match = packages_regex.search(response)
    if packages_match:
        packages_content = packages_match.group(1).strip()
        # Split by newlines or commas
        packages_list = [
            pkg.strip() for pkg in re.split(r'[\n,]+', packages_content)
            if pkg.strip()
        ]
        for pkg in packages_list:
            if pkg not in sections["packages"]:
                sections["packages"].append(pkg)

    # Parse structure
    structure_match = re.search(r'<structure>([\s\S]*?)</structure>', response)
    if structure_match:
        sections["structure"] = structure_match.group(1).strip()

    # Parse explanation
    explanation_match = re.search(r'<explanation>([\s\S]*?)</explanation>', response)
    if explanation_match:
        sections["explanation"] = explanation_match.group(1).strip()

    # Parse template
    template_match = re.search(r'<template>(.*?)</template>', response)
    if template_match:
        sections["template"] = template_match.group(1).strip()

    print(f"[parse_ai_response] FINAL RESULT: Parsed {len(sections['files'])} files, {len(sections['packages'])} packages")
    for f in sections['files']:
        print(f"[parse_ai_response]   {f['path']} ({len(f['content'])} chars)")
    
    return sections


# --------------------------
# Enhanced Streaming Response
# --------------------------
async def POST(request: Any):
    """Enhanced POST handler with better error handling and streaming"""
    
    # Parse request body
    try:
        if hasattr(request, "json"):
            body = await request.json()
        elif isinstance(request, dict):
            body = request
        else:
            body = {}
    except Exception as e:
        print(f"[apply-ai-code-stream] Error parsing request: {e}")
        body = {}

    response_text: str = body.get("response", "")
    is_edit: bool = body.get("isEdit", False)
    packages_in = body.get("packages", []) or []
    sandbox_id = body.get("sandboxId")

    if not response_text:
        error_response = {"error": "response is required", "status": 400}
        if JSONResponse is None:
            return error_response
        return JSONResponse(content=error_response, status_code=400)

    print(f"[apply-ai-code-stream] Processing {len(response_text)} chars, isEdit: {is_edit}")

    # Parse AI response with FIXED parser
    try:
        parsed = parse_ai_response(response_text)
        print(f"[apply-ai-code-stream] FIXED parser found {len(parsed['files'])} files successfully")
    except Exception as e:
        print(f"[apply-ai-code-stream] Parse error: {e}")
        error_response = {
            "success": False,
            "error": f"Failed to parse AI response: {str(e)}",
            "results": {"filesCreated": [], "packagesInstalled": [], "commandsExecuted": [], "errors": [str(e)]},
        }
        if JSONResponse is None:
            return error_response
        return JSONResponse(content=error_response, status_code=500)

    # Ensure globals exist
    global existing_files, active_sandbox, sandbox_data, sandbox_state, conversation_state
    if existing_files is None:
        existing_files = set()

    # Get/Connect sandbox with better error handling
    sandbox = active_sandbox
    if not sandbox and sandbox_id:
        print(f"[apply-ai-code-stream] Attempting to reconnect to sandbox {sandbox_id}")
        if E2BSandbox is None:
            error_msg = "E2B Sandbox library not available"
            error_response = {
                "success": False,
                "error": error_msg,
                "results": {"filesCreated": [], "packagesInstalled": [], "commandsExecuted": [], "errors": [error_msg]},
            }
            if JSONResponse is None:
                return error_response
            return JSONResponse(content=error_response, status_code=500)

        try:
            # Try to reconnect to existing sandbox
            api_key = os.getenv("E2B_API_KEY")
            if hasattr(E2BSandbox, 'connect'):
                sandbox = await E2BSandbox.connect(sandbox_id, api_key=api_key)
            else:
                # Fallback for different SDK versions
                sandbox = E2BSandbox(api_key=api_key)
            
            active_sandbox = sandbox
            print(f"[apply-ai-code-stream] Successfully reconnected to sandbox {sandbox_id}")
            
            # Update sandbox_data if needed
            if sandbox_data is None:
                sandbox_data = {
                    "sandboxId": sandbox_id,
                    "url": f"https://localhost:5173"  # Default URL
                }

        except Exception as reconnect_error:
            print(f"[apply-ai-code-stream] Reconnection failed: {reconnect_error}")
            error_response = {
                "success": False,
                "error": f"Failed to reconnect to sandbox: {str(reconnect_error)}",
                "results": {"filesCreated": [], "packagesInstalled": [], "commandsExecuted": [], "errors": [str(reconnect_error)]},
            }
            if JSONResponse is None:
                return error_response
            return JSONResponse(content=error_response, status_code=500)

    if not sandbox:
        error_msg = "No active sandbox found"
        error_response = {
            "success": False,
            "error": error_msg,
            "results": {"filesCreated": [], "packagesInstalled": [], "commandsExecuted": [], "errors": [error_msg]},
        }
        if JSONResponse is None:
            return error_response
        return JSONResponse(content=error_response, status_code=200)
    
    cleanup_result = await clean_components_directory_before_generation(sandbox)
    # Enhanced streaming SSE
    async def event_stream():
        """Enhanced event stream with better error handling"""
        results = {
            "filesCreated": [],
            "filesUpdated": [],
            "packagesInstalled": [],
            "packagesAlreadyInstalled": [],
            "packagesFailed": [],
            "commandsExecuted": [],
            "errors": [],
        }

        async def send_progress(data: Dict[str, Any]):
            try:
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as e:
                print(f"[apply-ai-code-stream] Progress send error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': f'Progress error: {str(e)}'})}\n\n"

        try:
            # Start
            if cleanup_result.get("filesRemoved", 0) > 0:
                async for chunk in send_progress({
                    "type": "cleanup", 
                    "message": f"Cleaned {cleanup_result['filesRemoved']} old component files for fresh start",
                    "removedFiles": cleanup_result["removedFiles"]
                }):
                    yield chunk
            async for chunk in send_progress({"type": "start", "message": "Starting code application with FIXED parsing..."}):
                yield chunk

            # ... (package installation logic remains the same) ...
            packages_array = packages_in[:] if isinstance(packages_in, list) else []
            parsed_pkgs = parsed.get("packages") or []
            all_pkgs = [p for p in packages_array if isinstance(p, str)] + [p for p in parsed_pkgs if isinstance(p, str)]
            
            unique_pkgs = []
            seen = set()
            for p in all_pkgs:
                p = p.strip()
                if not p or p in ("react", "react-dom"):
                    continue
                if p not in seen:
                    seen.add(p)
                    unique_pkgs.append(p)

            # Install packages if detected
            if unique_pkgs:
                async for chunk in send_progress({
                    "type": "step", 
                    "step": 1.5, 
                    "message": f"Installing {len(unique_pkgs)} required packages..."
                }):
                    yield chunk
                
                try:
                    # Create install code directly in sandbox
                    install_code = f"""
            import subprocess
            import os
            import json

            os.chdir('/home/user/app')
            packages = {json.dumps(unique_pkgs)}

            print("Installing packages:", packages)
            result = subprocess.run(['npm', 'install'] + packages + ['--legacy-peer-deps'], 
                                capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                print("SUCCESS: Packages installed")
            else:
                print("ERROR:", result.stderr)
                
            print("INSTALL_COMPLETE")
            """
                    
                    install_result = await _run_in_sandbox(sandbox, install_code)
                    install_output = _extract_output_text(install_result)
                    
                    if "SUCCESS: Packages installed" in install_output:
                        async for chunk in send_progress({
                            "type": "success", 
                            "message": f"Successfully installed: {', '.join(unique_pkgs)}"
                        }):
                            yield chunk
                    else:
                        async for chunk in send_progress({
                            "type": "warning", 
                            "message": f"Package installation had issues"
                        }):
                            yield chunk
                            
                except Exception as e:
                    print(f"[apply-ai-code-stream] Package installation error: {e}")
                    async for chunk in send_progress({
                        "type": "warning", 
                        "message": f"Package installation failed: {str(e)}"
                    }):
                        yield chunk


            # Enhanced file processing - ENSURE APP STRUCTURE
            files_array = parsed.get("files") or []

            # Verify App.jsx is included for component edits
            if is_edit and files_array:
                has_app_jsx = any('App.jsx' in f.get('path', '') for f in files_array)
                has_component_files = any('components/' in f.get('path', '') for f in files_array)
                
                if has_component_files and not has_app_jsx:
                    print("[apply-ai-code-stream] WARNING: Component edited but no App.jsx - application structure may break")

            async for chunk in send_progress({
                "type": "step",
                "step": 2,
                "message": f"Creating {len(files_array)} files with FIXED parsing..."
            }):
                yield chunk

            for idx, file in enumerate(files_array):
                try:
                    fpath = (file.get("path") or "").strip()
                    fcontent = file.get("content") or ""
                    
                    if not fpath or not fcontent:
                        print(f"[apply-ai-code-stream] Skipping empty file: {fpath}")
                        continue

                    async for chunk in send_progress({
                        "type": "file-progress",
                        "current": idx + 1,
                        "total": len(files_array),
                        "fileName": fpath,
                        "action": "creating"
                    }):
                        yield chunk

                    # Normalize path
                    if fpath.startswith("/"):
                        fpath = fpath[1:]
                    
                    base_name = fpath.split("/")[-1] if fpath else ""
                    config_files = {
                        "tailwind.config.js", "vite.config.js", "package.json",
                        "package-lock.json", "tsconfig.json", "postcss.config.js"
                    }
                    if base_name in config_files:
                        print(f"[apply-ai-code-stream] Skipping config file: {fpath}")
                        continue
                    
                    if not (fpath.startswith("src/") or fpath.startswith("public/") or fpath == "index.html"):
                        fpath = "src/" + fpath

                    if re.search(r"\.(jsx?|tsx?)$", fpath):
                        fcontent = re.sub(r"""import\s+['"]\./[^'"]+\.css['"];?\s*\n?""", "", fcontent)

                    # CRITICAL FIX: Sanitize content to prevent UTF-8 encoding errors
                    fcontent = sanitize_and_validate_jsx(fcontent, fpath)

                    is_update = fpath in (existing_files or set())
                    full_path = f"/home/user/app/{fpath}"
                    
                    try:
                        escaped_content = json.dumps(fcontent, ensure_ascii=False)
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        print(f"[apply-ai-code-stream] Unicode error for {fpath}, applying aggressive sanitization")
                        fcontent = fcontent.encode('ascii', errors='ignore').decode('ascii')
                        escaped_content = json.dumps(fcontent)

                    write_code = f"""
import os
import json

file_path = "{full_path}"
file_content = {escaped_content}

try:
    if isinstance(file_content, str):
        file_content.encode('utf-8')
    
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(file_content)
    
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            written_content = f.read()
        
        if len(written_content) > 0:
            print("SUCCESS: File written and verified")
            print(f"WRITE_RESULT:{{json.dumps({{"path": "{fpath}", "size": len(written_content), "success": True}})}}")
        else:
            print("ERROR: File exists but is empty")
            print(f"WRITE_RESULT:{{json.dumps({{"path": "{fpath}", "success": False, "error": "Empty file"}})}}")
    else:
        print("ERROR: File was not created")
        print(f"WRITE_RESULT:{{json.dumps({{"path": "{fpath}", "success": False, "error": "File not created"}})}}")
    
except UnicodeEncodeError as e:
    print(f"ERROR: Unicode encoding error: {{str(e)}}")
    print(f"WRITE_RESULT:{{json.dumps({{"path": "{fpath}", "success": False, "error": f"Unicode encoding error: {{str(e)}}"}})}}")
except Exception as e:
    print(f"ERROR: Failed to write file: {{str(e)}}")
    print(f"WRITE_RESULT:{{json.dumps({{"path": "{fpath}", "success": False, "error": str(e)}})}}")
"""
                    write_result = await _run_in_sandbox(sandbox, write_code)
                    write_output = _extract_output_text(write_result)
                    
                    print(f"[apply-ai-code-stream] Write output for {fpath}: {write_output}")
                    
                    write_success = False
                    for line in write_output.splitlines():
                        if line.startswith("WRITE_RESULT:"):
                            try:
                                result_data = json.loads(line[len("WRITE_RESULT:"):])
                                write_success = result_data.get("success", False)
                                break
                            except:
                                pass
                    
                    if not write_success:
                        write_success = "SUCCESS:" in write_output and "ERROR:" not in write_output
                    
                    if write_success:
                        await asyncio.sleep(0.1)
                        if is_update:
                            results["filesUpdated"].append(fpath)
                        else:
                            results["filesCreated"].append(fpath)
                            (existing_files or set()).add(fpath)

                        async for chunk in send_progress({
                            "type": "file-complete",
                            "fileName": fpath,
                            "action": "updated" if is_update else "created"
                        }):
                            yield chunk
                        
                        print(f"[apply-ai-code-stream] Successfully wrote {fpath}")
                    else:
                        error_msg = f"Failed to write {fpath}"
                        results["errors"].append(error_msg)
                        print(f"[apply-ai-code-stream] {error_msg}: {write_output}")

                except Exception as e:
                    error_msg = f"Failed to create {file.get('path')}: {str(e)}"
                    results["errors"].append(error_msg)
                    print(f"[apply-ai-code-stream] {error_msg}")
                if idx < len(files_array) - 1:  # Don't delay after last file
                   await asyncio.sleep(0.2)    
            if results["filesCreated"] or results["filesUpdated"]:
                print("[apply-ai-code-stream] File changes detected, saving state...")
                
                # CRITICAL FIX: Update file cache immediately after file creation
                jsx_files = [f for f in (results["filesCreated"] + results["filesUpdated"]) if f.endswith('.jsx')]
                            
                if jsx_files:
                    debug_output = await debug_component_content(sandbox, jsx_files)
                    
                    # If smart quotes are found, report it
                    if "Has smart quotes: True" in debug_output:
                        print("[apply-ai-code-stream] WARNING: Smart quotes detected in components!")
                        
                    # If missing imports/exports, report it
                    if "Has React import: False" in debug_output:
                        print("[apply-ai-code-stream] WARNING: Missing React imports detected!")
                async for chunk in send_progress({ "type": "step", "step": 3, "message": "Updating file cache for future edits..." }):
                    yield chunk
                
                try:
                    # Get updated files from sandbox
                    main_app = sys.modules.get("main")
                    if main_app and hasattr(main_app, "MODULES"):
                        get_files_module = main_app.MODULES.get("get_sandbox_files")
                        if get_files_module:
                            cache_result = await get_files_module.GET()
                            
                            if cache_result.get("success") and cache_result.get("manifest"):
                                # Ensure sandbox_state exists and update file cache
                                global sandbox_state
                                if sandbox_state is None:
                                    sandbox_state = {}
                                
                                if "fileCache" not in sandbox_state:
                                    sandbox_state["fileCache"] = {}
                                
                                sandbox_state["fileCache"]["manifest"] = cache_result["manifest"]
                                sandbox_state["fileCache"]["files"] = cache_result["manifest"]["files"]
                                
                                files_count = len(cache_result["manifest"]["files"])
                                print(f"[apply-ai-code-stream] ✅ File cache updated with {files_count} files")
                                
                                async for chunk in send_progress({ "type": "success", "message": f"File cache updated with {files_count} files - ready for edits" }):
                                    yield chunk
                            else:
                                print("[apply-ai-code-stream] ❌ Failed to update file cache")
                                async for chunk in send_progress({ "type": "warning", "message": "File cache update failed - edits may not work" }):
                                    yield chunk
                        
                        # save_state(main_app.MODULES)
                        
                except Exception as e:
                    print(f"[apply-ai-code-stream] File cache update error: {e}")
                    async for chunk in send_progress({ "type": "warning", "message": "File cache update failed" }):
                        yield chunk
                # ... (command execution logic remains the same) ...
            
            # Complete - ONLY restart Vite once after all files are written
            if results["filesCreated"] or results["filesUpdated"]:
                async for chunk in send_progress({ "type": "step", "step": 4, "message": "Restarting Vite to reflect all changes..." }):
                    yield chunk
                
                all_changed_files = results["filesCreated"] + results["filesUpdated"]
                changed_file_paths = [f"/home/user/app/{f}" for f in all_changed_files if f.startswith("src/")]
                
                reload_success = await force_vite_reload_after_changes(sandbox, changed_file_paths)
                
                if reload_success:
                    async for chunk in send_progress({ "type": "success", "message": "Vite restarted - changes should be visible" }):
                        yield chunk
                else:
                    async for chunk in send_progress({ "type": "warning", "message": "Vite restart failed - try manual refresh" }):
                        yield chunk

            # Final completion
            async for chunk in send_progress({
                "type": "complete",
                "results": results,
                "explanation": parsed.get("explanation"),
                "structure": parsed.get("structure"),
                "message": f"Successfully applied {len(results['filesCreated']) + len(results['filesUpdated'])} files!"
            }):
                yield chunk

        except Exception as e:
            print(f"[apply-ai-code-stream] Stream error: {e}")
            async for chunk in send_progress({
                "type": "error",
                "message": f"Application failed: {str(e)}"
            }):
                yield chunk

    # Return streaming response
    if StreamingResponse is None:
        return {"error": "StreamingResponse not available", "status": 500}

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )