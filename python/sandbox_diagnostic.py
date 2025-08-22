#!/usr/bin/env python3
"""
Sandbox Diagnostic Script
Run this to test sandbox file operations and identify issues
"""

import os
import json
import asyncio
from typing import Any, Dict

# Import your sandbox modules (adjust paths as needed)
try:
    from e2b import Sandbox as E2BSandbox
except ImportError:
    try:
        from e2b_code_interpreter import Sandbox as E2BSandbox
    except ImportError:
        print("❌ E2B library not found. Install with: pip install e2b_code_interpreter")
        exit(1)

async def test_sandbox_operations():
    """Test basic sandbox operations"""
    print("🔍 Starting Sandbox Diagnostic...")
    
    # Test 1: Create sandbox
    print("\n1. Testing sandbox creation...")
    try:
        api_key = os.getenv("E2B_API_KEY")
        if not api_key:
            print("❌ E2B_API_KEY environment variable not set")
            return
            
        sandbox = E2BSandbox(api_key=api_key)
        print(f"✅ Sandbox created: {getattr(sandbox, 'sandbox_id', 'Unknown ID')}")
    except Exception as e:
        print(f"❌ Sandbox creation failed: {e}")
        return
    
    # Test 2: Basic code execution
    print("\n2. Testing basic code execution...")
    try:
        # Find the correct run method
        run_method = None
        for method_name in ['run_code', 'runCode', 'run', 'exec']:
            if hasattr(sandbox, method_name):
                run_method = getattr(sandbox, method_name)
                print(f"✅ Found run method: {method_name}")
                break
        
        if not run_method:
            print("❌ No run method found on sandbox")
            return
            
        # Execute simple test
        result = run_method("print('Hello from sandbox!')")
        
        # Handle execution result
        if hasattr(result, 'wait'):
            print("⏳ Waiting for execution to complete...")
            result.wait()
        
        # Extract output
        output = ""
        if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
            if isinstance(result.logs.stdout, list):
                output = ''.join(result.logs.stdout)
            else:
                output = str(result.logs.stdout)
        elif hasattr(result, 'output'):
            output = str(result.output)
        
        print(f"✅ Execution output: {output.strip()}")
        
    except Exception as e:
        print(f"❌ Code execution failed: {e}")
        return
    
    # Test 3: File operations
    print("\n3. Testing file operations...")
    try:
        file_test_code = """
import os
import json

# Test directory structure
print("Testing file operations...")

# Create test directory
test_dir = "/home/user/app/src/test"
os.makedirs(test_dir, exist_ok=True)

# Create test file
test_file = "/home/user/app/src/test/TestComponent.jsx"
test_content = '''import React from 'react';

function TestComponent() {
  return (
    <div className="test-component">
      <h1>Test Component</h1>
    </div>
  );
}

export default TestComponent;'''

with open(test_file, 'w') as f:
    f.write(test_content)

# Verify file was created
if os.path.exists(test_file):
    with open(test_file, 'r') as f:
        written_content = f.read()
    
    print(f"SUCCESS: File created and verified")
    print(f"File size: {len(written_content)} characters")
    print(f"RESULT: {json.dumps({'success': True, 'size': len(written_content)})}")
else:
    print(f"ERROR: File was not created")
    print(f"RESULT: {json.dumps({'success': False, 'error': 'File not found'})}")
"""
        
        result = run_method(file_test_code)
        
        if hasattr(result, 'wait'):
            result.wait()
        
        # Extract output
        output = ""
        if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
            if isinstance(result.logs.stdout, list):
                output = ''.join(result.logs.stdout)
            else:
                output = str(result.logs.stdout)
        elif hasattr(result, 'output'):
            output = str(result.output)
        
        print(f"File operation result: {output}")
        
        # Parse result
        if "SUCCESS:" in output:
            print("✅ File operations working correctly")
        else:
            print("❌ File operations failed")
            
    except Exception as e:
        print(f"❌ File operation test failed: {e}")
    
    # Test 4: Directory listing
    print("\n4. Testing directory listing...")
    try:
        list_code = """
import os
import json

app_dir = "/home/user/app"
if os.path.exists(app_dir):
    files = []
    for root, dirs, filenames in os.walk(app_dir):
        # Skip node_modules
        dirs[:] = [d for d in dirs if d != 'node_modules']
        
        for filename in filenames:
            if filename.endswith(('.jsx', '.js', '.css', '.json')):
                rel_path = os.path.relpath(os.path.join(root, filename), app_dir)
                files.append(rel_path)
    
    print(f"FOUND_FILES: {json.dumps(files)}")
else:
    print("ERROR: App directory not found")
"""
        
        result = run_method(list_code)
        
        if hasattr(result, 'wait'):
            result.wait()
        
        # Extract output
        output = ""
        if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
            if isinstance(result.logs.stdout, list):
                output = ''.join(result.logs.stdout)
            else:
                output = str(result.logs.stdout)
        elif hasattr(result, 'output'):
            output = str(result.output)
        
        print(f"Directory listing result: {output}")
        
        # Parse files
        for line in output.splitlines():
            if line.startswith("FOUND_FILES:"):
                try:
                    files = json.loads(line[len("FOUND_FILES:"):])
                    print(f"✅ Found {len(files)} files in sandbox")
                    for f in files[:5]:  # Show first 5
                        print(f"   - {f}")
                    if len(files) > 5:
                        print(f"   ... and {len(files) - 5} more")
                except:
                    print("❌ Could not parse file list")
                break
        else:
            print("❌ No file list found in output")
            
    except Exception as e:
        print(f"❌ Directory listing test failed: {e}")
    
    # Test 5: Package installation
    print("\n5. Testing package installation...")
    try:
        npm_test_code = """
import subprocess
import os

os.chdir('/home/user/app')

try:
    # Check if npm is available
    result = subprocess.run(['npm', '--version'], capture_output=True, text=True, timeout=10)
    
    if result.returncode == 0:
        print(f"NPM version: {result.stdout.strip()}")
        
        # Test package.json exists
        if os.path.exists('package.json'):
            print("package.json exists")
            
            # Try to install a simple package
            install_result = subprocess.run(
                ['npm', 'install', 'lodash', '--save'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if install_result.returncode == 0:
                print("SUCCESS: Package installation working")
            else:
                print(f"ERROR: Package installation failed: {install_result.stderr}")
        else:
            print("ERROR: package.json not found")
    else:
        print(f"ERROR: npm not available: {result.stderr}")
        
except Exception as e:
    print(f"ERROR: {str(e)}")
"""
        
        result = run_method(npm_test_code)
        
        if hasattr(result, 'wait'):
            result.wait()
        
        # Extract output
        output = ""
        if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
            if isinstance(result.logs.stdout, list):
                output = ''.join(result.logs.stdout)
            else:
                output = str(result.logs.stdout)
        elif hasattr(result, 'output'):
            output = str(result.output)
        
        print(f"Package installation test: {output}")
        
        if "SUCCESS:" in output:
            print("✅ Package installation working")
        else:
            print("❌ Package installation issues detected")
            
    except Exception as e:
        print(f"❌ Package installation test failed: {e}")
    
    print("\n🎉 Diagnostic complete!")
    
    # Cleanup
    try:
        if hasattr(sandbox, 'kill'):
            sandbox.kill()
        elif hasattr(sandbox, 'close'):
            sandbox.close()
        print("✅ Sandbox cleaned up")
    except:
        print("⚠️  Could not clean up sandbox")

def test_file_parsing():
    """Test the file parsing logic"""
    print("\n📝 Testing file parsing logic...")
    
    # Import the fixed parse function
    try:
        import sys
        import os
        
        # Add the routes directory to Python path to import our modules
        current_dir = os.path.dirname(os.path.abspath(__file__))
        routes_dir = os.path.join(current_dir, 'routes')
        sys.path.insert(0, routes_dir)
        
        # Import from the routes folder
        
        from routes/apply_ai_code_stream import parse_ai_response
        
        # Test response with files
        test_response = """
<file path="src/App.jsx">
import React from 'react';
import Header from './components/Header';

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
    </div>
  );
}

export default App;
</file>

<file path="src/components/Header.jsx">
import React from 'react';

function Header() {
  return (
    <header className="bg-white shadow-md">
      <h1>My App</h1>
    </header>
  );
}

export default Header;
</file>
"""
        
        parsed = parse_ai_response(test_response)
        
        print(f"✅ Parsed {len(parsed['files'])} files:")
        for file in parsed['files']:
            print(f"   - {file['path']} ({len(file['content'])} chars)")
        
        # Check for duplicates
        paths = [f['path'] for f in parsed['files']]
        unique_paths = set(paths)
        
        if len(paths) == len(unique_paths):
            print("✅ No duplicate files detected")
        else:
            print(f"❌ Found {len(paths) - len(unique_paths)} duplicate files")
            
    except ImportError as e:
        print(f"❌ Could not import parsing function: {e}")
        print("Make sure apply_ai_code_stream.py is in the routes/ directory")
    except Exception as e:
        print(f"❌ File parsing test failed: {e}")

if __name__ == "__main__":
    print("🚀 Sandbox Diagnostic Tool")
    print("=" * 50)
    
    # Test file parsing first (doesn't need sandbox)
    test_file_parsing()
    
    # Test sandbox operations
    try:
        asyncio.run(test_sandbox_operations())
    except KeyboardInterrupt:
        print("\n⚠️  Diagnostic interrupted by user")
    except Exception as e:
        print(f"\n❌ Diagnostic failed: {e}")