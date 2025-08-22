from typing import TypedDict, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain.schema.runnable import RunnableLambda

active_sandbox: Optional[Any] = None

class GraphState(TypedDict, total=False):
    payload: Dict[str, Any]
    response: Dict[str, Any]

_CREATE_ZIP_CODE = """
import zipfile
import os
import json

print("=== ZIP CREATION STARTED ===")

app_dir = '/home/user/app'
if not os.path.exists(app_dir):
    print(f"ERROR: {app_dir} does not exist!")
    exit(1)

os.chdir(app_dir)
print(f"Working in: {os.getcwd()}")

# Find all project files
project_files = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '.next', 'dist', 'build', '__pycache__']]
    
    for file in files:
        if not file.startswith('.') and not file.endswith('.pyc'):
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, '.')
            if os.path.isfile(file_path):
                project_files.append((file_path, rel_path))

print(f"Found {len(project_files)} files to zip")

# Create zip
zip_path = '/tmp/project.zip'
if os.path.exists(zip_path):
    os.remove(zip_path)

files_added = 0
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
    for file_path, arc_name in project_files:
        try:
            zipf.write(file_path, arc_name)
            files_added += 1
        except Exception as e:
            print(f"Error adding {file_path}: {e}")

if os.path.exists(zip_path):
    file_size = os.path.getsize(zip_path)
    print(f"ZIP_SUCCESS:{file_size}:{files_added}")
else:
    print("ZIP_FAILED:0:0")
"""

_READ_AND_B64_CODE = """
import base64
import os

zip_path = '/tmp/project.zip'
try:
    if os.path.exists(zip_path):
        with open(zip_path, 'rb') as f:
            content = f.read()
            if len(content) > 0:
                encoded = base64.b64encode(content).decode('utf-8')
                print(f"BASE64_START")
                print(encoded)
                print(f"BASE64_END")
            else:
                print("EMPTY_FILE")
    else:
        print("FILE_NOT_FOUND")
except Exception as e:
    print(f"READ_ERROR:{e}")
"""

def _extract_output_text(result: Any) -> str:
    """Extract output text from various sandbox result formats"""
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
    
    # Handle E2B execution objects
    if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
        if isinstance(result.logs.stdout, list):
            return "".join(str(x) for x in result.logs.stdout)
        else:
            return str(result.logs.stdout or "")
    elif hasattr(result, 'output'):
        return str(result.output or "")
    
    return str(result) if result else ""

def _compute(_: Dict[str, Any]) -> Dict[str, Any]:
    if active_sandbox is None:
        return {"success": False, "error": "No active sandbox"}
    
    print("[create-zip] Creating project zip...")
    
    try:
        # Step 1: Create zip file
        create_result = active_sandbox.run_code(_CREATE_ZIP_CODE)
        create_output = _extract_output_text(create_result)
        
        print(f"[create-zip] Creation output: {create_output}")
        
        # Check if zip creation was successful
        if "ZIP_SUCCESS:" not in create_output:
            return {
                "success": False,
                "error": "Zip creation failed",
                "debug": create_output
            }
        
        # Step 2: Read and encode zip file
        read_result = active_sandbox.run_code(_READ_AND_B64_CODE)
        read_output = _extract_output_text(read_result)
        
        print(f"[create-zip] Read output length: {len(read_output)}")
        
        # Extract base64 content between markers
        if "BASE64_START" in read_output and "BASE64_END" in read_output:
            lines = read_output.split('\n')
            base64_lines = []
            capturing = False
            
            for line in lines:
                if line.strip() == "BASE64_START":
                    capturing = True
                    continue
                elif line.strip() == "BASE64_END":
                    break
                elif capturing:
                    base64_lines.append(line.strip())
            
            base64_content = "".join(base64_lines)
            
            if len(base64_content) < 100:
                return {
                    "success": False,
                    "error": "Base64 content too short, zip may be empty",
                    "debug": read_output
                }
            
            # Validate base64
            try:
                import base64 as b64
                b64.b64decode(base64_content)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Invalid base64 content: {e}",
                    "debug": read_output
                }
            
            # Return proper data URL
            data_url = f"data:application/zip;base64,{base64_content}"
            
            return {
                "success": True,
                "dataUrl": data_url,
                "fileName": "project.zip",
                "message": "Zip file created successfully"
            }
        else:
            return {
                "success": False,
                "error": "Could not find base64 content markers",
                "debug": read_output
            }
            
    except Exception as e:
        print(f"[create-zip] Error: {e}")
        return {"success": False, "error": str(e)}

_processor = RunnableLambda(_compute)

def _node(state: GraphState) -> GraphState:
    resp = _processor.invoke(state.get("payload", {}))
    return {"response": resp}

_sg = StateGraph(GraphState)
_sg.add_node("process", _node)
_sg.set_entry_point("process")
_sg.add_edge("process", END)
_graph = _sg.compile()

def POST() -> Dict[str, Any]:
    result = _graph.invoke({})
    return result["response"]