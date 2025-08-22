# test_hosting_fixes.py - Test script to verify the fixes work

import asyncio
import sys
import os

# Add your routes directory to path if needed
sys.path.append('routes')

async def test_create_sandbox():
    """Test the create sandbox functionality"""
    print("🧪 Testing create-ai-sandbox...")
    
    try:
        # Import your fixed create sandbox module
        from create_ai_sandbox import POST as create_sandbox
        
        # Test sandbox creation
        result = await create_sandbox()
        
        if result.get("success"):
            print("✅ Sandbox creation: SUCCESS")
            print(f"   Sandbox ID: {result.get('sandboxId')}")
            print(f"   URL: {result.get('url')}")
            print(f"   Vite Running: {result.get('viteRunning')}")
            print(f"   Accessible: {result.get('accessible')}")
            return result
        else:
            print("❌ Sandbox creation: FAILED")
            print(f"   Error: {result.get('error')}")
            return None
            
    except Exception as e:
        print(f"❌ Sandbox creation: ERROR - {e}")
        return None

async def test_restart_vite():
    """Test the restart Vite functionality"""
    print("\n🧪 Testing restart-vite...")
    
    try:
        # Import your fixed restart vite module
        from restart_vite import POST as restart_vite
        
        # Test restart
        result = await restart_vite()
        
        if result.get("success"):
            print("✅ Vite restart: SUCCESS")
            print(f"   External access configured: {result.get('external_access_configured')}")
            print(f"   External access verified: {result.get('external_access_verified')}")
            print(f"   Status: {result.get('restart_status')}")
        else:
            print("❌ Vite restart: FAILED")
            print(f"   Error: {result.get('error')}")
            
        return result
        
    except Exception as e:
        print(f"❌ Vite restart: ERROR - {e}")
        return None

async def test_sandbox_status():
    """Test sandbox status check"""
    print("\n🧪 Testing sandbox-status...")
    
    try:
        # Import sandbox status if available
        from sandbox_status import get_sandbox_status
        
        result = get_sandbox_status()
        
        if result.get("success"):
            print("✅ Sandbox status: SUCCESS")
            print(f"   Active: {result.get('active')}")
            print(f"   Healthy: {result.get('healthy')}")
        else:
            print("❌ Sandbox status: FAILED")
            print(f"   Error: {result.get('error')}")
            
        return result
        
    except Exception as e:
        print(f"❌ Sandbox status: ERROR - {e}")
        return None

def check_environment():
    """Check if environment is properly set up"""
    print("🔍 Checking environment...")
    
    # Check E2B API key
    api_key = os.getenv("E2B_API_KEY")
    if api_key:
        print("✅ E2B_API_KEY is set")
    else:
        print("❌ E2B_API_KEY is missing")
        print("   Please set your E2B API key: export E2B_API_KEY=your_key")
    
    # Check if E2B is installed
    try:
        import e2b_code_interpreter
        print("✅ e2b_code_interpreter is installed")
    except ImportError:
        try:
            import e2b
            print("✅ e2b is installed")
        except ImportError:
            print("❌ E2B library not found")
            print("   Please install: pip install e2b-code-interpreter")
    
    # Check if required files exist
    required_files = [
        'routes/create-ai-sandbox.py',
        'routes/restart-vite.py'
    ]
    
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
    
    return api_key is not None

async def run_comprehensive_test():
    """Run all tests in sequence"""
    print("🚀 Starting comprehensive hosting fix tests...\n")
    
    # Check environment first
    if not check_environment():
        print("\n❌ Environment check failed. Please fix the issues above.")
        return
    
    print("\n" + "="*50)
    
    # Test 1: Create sandbox
    sandbox_result = await test_create_sandbox()
    
    # Test 2: Restart Vite (only if sandbox created)
    if sandbox_result and sandbox_result.get("success"):
        await asyncio.sleep(2)  # Brief pause
        restart_result = await test_restart_vite()
    else:
        print("\n⚠️ Skipping restart test - sandbox creation failed")
        restart_result = None
    
    # Test 3: Check status
    await asyncio.sleep(1)
    status_result = await test_sandbox_status()
    
    # Summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY:")
    
    if sandbox_result and sandbox_result.get("success"):
        print("✅ Sandbox Creation: PASSED")
    else:
        print("❌ Sandbox Creation: FAILED")
    
    if restart_result and restart_result.get("success"):
        print("✅ Vite Restart: PASSED")
    else:
        print("❌ Vite Restart: FAILED")
    
    if status_result and status_result.get("success"):
        print("✅ Status Check: PASSED")
    else:
        print("❌ Status Check: FAILED")
    
    # Overall assessment
    all_passed = all([
        sandbox_result and sandbox_result.get("success"),
        restart_result and restart_result.get("success"),
        status_result and status_result.get("success")
    ])
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED! Your hosting fixes are working correctly.")
        if sandbox_result:
            print(f"\n🌐 Your app should be accessible at: {sandbox_result.get('url')}")
    else:
        print("\n⚠️ Some tests failed. Check the output above for details.")
        print("\nCommon fixes:")
        print("1. Ensure E2B_API_KEY is set correctly")
        print("2. Check that the fixed files are in the right location")
        print("3. Restart your FastAPI server after making changes")
        print("4. Check E2B account credits and permissions")

def run_quick_verification():
    """Quick verification without creating actual sandbox"""
    print("🔍 Quick verification of fixes...")
    
    try:
        # Check if files have the fixes
        fixes_found = 0
        total_fixes = 0
        
        # Check create-ai-sandbox.py
        try:
            with open('routes/create-ai-sandbox.py', 'r') as f:
                content = f.read()
                
                total_fixes += 4
                
                if 'host: "0.0.0.0"' in content or "host: '0.0.0.0'" in content:
                    if 'hmr:' in content:
                        fixes_found += 1
                        print("✅ HMR configuration fix found")
                
                if 'viteStartupDelay=8000' in content or 'viteStartupDelay.*8' in content:
                    fixes_found += 1
                    print("✅ Startup timing fix found")
                
                if content.count('e2b.dev') >= 3:
                    fixes_found += 1
                    print("✅ URL discovery improvements found")
                
                if '_extract_output_text' in content and 'Logs' in content:
                    fixes_found += 1
                    print("✅ Output extraction fix found")
                    
        except FileNotFoundError:
            print("❌ create-ai-sandbox.py not found")
        
        # Check restart-vite.py
        try:
            with open('routes/restart-vite.py', 'r') as f:
                content = f.read()
                
                total_fixes += 2
                
                if 'VITE_HOST' in content and 'VITE_PORT' in content:
                    fixes_found += 1
                    print("✅ Environment variables fix found")
                
                if '_extract_output_safe' in content:
                    fixes_found += 1
                    print("✅ Safe output extraction fix found")
                    
        except FileNotFoundError:
            print("❌ restart-vite.py not found")
        
        print(f"\n📊 Fixes applied: {fixes_found}/{total_fixes}")
        
        if fixes_found == total_fixes:
            print("🎉 All fixes are present!")
        elif fixes_found > total_fixes // 2:
            print("⚠️ Most fixes are present, but some may be missing")
        else:
            print("❌ Many fixes are missing. Please apply the corrected versions.")
            
    except Exception as e:
        print(f"❌ Verification error: {e}")

if __name__ == "__main__":
    print("E2B Hosting Fix Test Suite")
    print("Choose test mode:")
    print("1. Quick verification (check fixes without running)")
    print("2. Comprehensive test (create sandbox and test)")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        run_quick_verification()
    elif choice == "2":
        asyncio.run(run_comprehensive_test())
    else:
        print("Invalid choice. Running quick verification...")
        run_quick_verification()