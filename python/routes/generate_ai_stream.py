# routes/generate_ai_stream.py - FIXED with robust file parsing and EXACT TS PROMPTS
from __future__ import annotations

import os
import re
import json
import time
import asyncio
from typing import Dict, List, Optional, TypedDict, Any, AsyncGenerator

from dotenv import load_dotenv
from routes.database import get_sandbox_state

# LangChain core
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# LLM Providers
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

# LangGraph
from langgraph.graph import StateGraph, START, END

load_dotenv()

# -------------------------------------------------------------------
# Shared globals (will be filled by main_app sync after sandbox)
# -------------------------------------------------------------------
sandbox_state: Optional[Dict[str, Any]] = None
conversation_state: Optional["ConversationState"] = None

import csv
import random
import unicodedata
import time
def load_design_schemas():
    """Load schemas from CSV with detailed logging"""
    print("[schema] Starting to load design schemas from CSV...")
    try:
        schemas = []
        csv_path = 'schema.csv'
        print(f"[schema] Looking for CSV file at: {csv_path}")
        
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            row_count = 0
            
            for row in reader:
                row_count += 1
                # print(f"[schema] Processing row {row_count}")
                
                schema_json = row.get('JSON SCHEMA', '').strip()
                if not schema_json:
                    print(f"[schema] Row {row_count}: Empty JSON SCHEMA field, skipping")
                    continue
                
                try:
                    parsed_schema = json.loads(schema_json)
                    schemas.append(parsed_schema)
                    # print(f"[schema] Row {row_count}: Successfully parsed JSON schema")
                except json.JSONDecodeError as e:
                    print(f"[schema] Row {row_count}: Invalid JSON - {e}")
                    continue
                except Exception as e:
                    print(f"[schema] Row {row_count}: Error parsing - {e}")
                    continue
        
        print(f"[schema] Successfully loaded {len(schemas)} valid schemas from {row_count} total rows")
        return schemas
        
    except FileNotFoundError:
        print("[schema] ERROR: CSV file not found")
        return []
    except Exception as e:
        print(f"[schema] ERROR loading schemas: {e}")
        return []

def get_random_schema():
    """Get random schema for new designs with logging"""
    print("[schema] Selecting random schema for new design...")
    
    schemas = load_design_schemas()
    if not schemas:
        print("[schema] No schemas available - design will use defaults")
        return None
    
    selected_schema = random.choice(schemas)
    schema_preview = str(selected_schema)[:200] + "..." if len(str(selected_schema)) > 200 else str(selected_schema)
    print(f"[schema] Selected schema: {schema_preview}")
    print(f"[schema] Schema contains {len(selected_schema)} top-level keys")
    
    return selected_schema

def is_redesign_request(prompt):
    """Check if user wants complete redesign with logging"""
    print(f"[schema] Checking if prompt is redesign request: '{prompt[:100]}...'")
    
    keywords = ['redesign', 'recreate', 'rebuild', 'start over', 'from scratch', 'new design', 're-design']
    prompt_lower = prompt.lower()
    
    found_keywords = []
    for keyword in keywords:
        if keyword in prompt_lower:
            found_keywords.append(keyword)
    
    is_redesign = len(found_keywords) > 0
    
    if is_redesign:
        print(f"[schema] REDESIGN DETECTED - Found keywords: {found_keywords}")
    else:
        print("[schema] Not a redesign request - treating as edit or new design")
    
    return is_redesign

async def clear_cache_and_files():
    """COMPREHENSIVE file cleanup - delete ALL src files, not just cached ones"""
    print("[schema] COMPREHENSIVE file cleanup for redesign...")
    
    global sandbox_state, active_sandbox
    
    if active_sandbox:
        # Delete ALL files in src directory, not just cached ones
        comprehensive_delete_code = f"""
import os
import shutil

print("=== COMPREHENSIVE FILE DELETION FOR REDESIGN ===")

# Delete entire src directory and recreate it
src_dir = "/home/user/app/src"
if os.path.exists(src_dir):
    try:
        shutil.rmtree(src_dir)
        print(f"DELETED: Entire src directory")
    except Exception as e:
        print(f"ERROR deleting src dir: {{e}}")

# Recreate empty src directory
os.makedirs(src_dir, exist_ok=True)
print("CREATED: Empty src directory")

# Also clean up any component-related files in root
root_files = ["/home/user/app/App.jsx", "/home/user/app/index.css"]
for file_path in root_files:
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"DELETED: {{file_path}}")
    except Exception as e:
        print(f"ERROR deleting {{file_path}}: {{e}}")

print("COMPREHENSIVE_DELETION_COMPLETE")
"""
        
        try:
            from routes.apply_ai_code_stream import _run_in_sandbox
            result = await _run_in_sandbox(active_sandbox, comprehensive_delete_code)
            
            if hasattr(result, 'logs') and hasattr(result.logs, 'stdout'):
                output = ''.join(result.logs.stdout) if isinstance(result.logs.stdout, list) else str(result.logs.stdout or "")
            else:
                output = str(result)
            
            print(f"[schema] Comprehensive deletion result: {output}")
                
        except Exception as e:
            print(f"[schema] ERROR in comprehensive deletion: {e}")
    
    # Clear the file cache completely
    if sandbox_state and isinstance(sandbox_state, dict):
        try:
            cache = sandbox_state.get("fileCache", {})
            if isinstance(cache, dict):
                cache.clear()  # Clear everything
                cache["files"] = {}
                cache["manifest"] = {}
                cache["lastSync"] = int(time.time() * 1000)
                
                print("[schema] File cache completely cleared")
        except Exception as e:
            print(f"[schema] ERROR clearing cache: {e}")

# Update the sync version for non-async contexts
def clear_cache():
    """Synchronous wrapper for cache clearing"""
    print("[schema] Synchronous cache clear requested - will clear cache only")
    global sandbox_state
    
    if not sandbox_state or not isinstance(sandbox_state, dict):
        print("[schema] No valid sandbox_state to clear")
        return
    
    try:
        cache = sandbox_state.get("fileCache", {})
        if isinstance(cache, dict):
            files_count = len(cache.get("files", {}))
            cache["files"] = {}
            cache["manifest"] = {}
            cache["lastSync"] = int(time.time() * 1000)
            print(f"[schema] Sync cache clear: removed {files_count} files from cache")
    except Exception as e:
        print(f"[schema] ERROR in sync cache clear: {e}")


def sanitize_content_for_utf8(content: str) -> str:
    """A more powerful sanitizer to remove smart quotes and bad whitespace."""
    if not isinstance(content, str):
        return str(content)

    # Comprehensive smart quote and special character replacement
    replacements = {
        '\u201c': '"', '\u201d': '"',  # “ ” -> "
        '\u2018': "'", '\u2019': "'",  # ‘ ’ -> '
        '\u2013': '-', '\u2014': '--', # – —
        '\u2026': '...',             # …
        '\u00a0': ' ',               # Non-breaking space
    }
    for old, new in replacements.items():
        content = content.replace(old, new)

    # Fix non-standard indentation by replacing leading unicode spaces with standard spaces
    cleaned_lines = []
    for line in content.splitlines():
        # Find the initial whitespace
        leading_whitespace = re.match(r'^\s+', line)
        if leading_whitespace:
            # Replace with standard spaces of the same length
            indent = ' ' * len(leading_whitespace.group(0))
            cleaned_lines.append(indent + line.lstrip())
        else:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)
def _file_cache() -> Dict[str, Any]:
    if isinstance(sandbox_state, dict):
        fc = sandbox_state.get("fileCache") or {}
        return fc if isinstance(fc, dict) else {}
    return {}

def _files_map() -> Dict[str, Any]:
    fc = _file_cache()
    files = fc.get("files")
    return files if isinstance(files, dict) else {}

def _manifest() -> Optional[Dict[str, Any]]:
    fc = _file_cache()
    m = fc.get("manifest")
    return m if isinstance(m, dict) else None

# -------------------------------------------------------------------
# Enhanced Conversation State
# -------------------------------------------------------------------
class ConversationState:
    def __init__(self):
        self.conversation_id = f"conv-{int(time.time())}"
        self.started_at = int(time.time())
        self.last_updated = int(time.time())
        self.context = {
            "messages": [],
            "edits": [],
            "project_evolution": {"major_changes": []},
            "user_preferences": {},
        }

# -------------------------------------------------------------------
# Enhanced Agent State
# -------------------------------------------------------------------
class AgentState(TypedDict):
    prompt: str
    model: str
    context: Dict
    is_edit: bool
    conversation_history: List[Dict]
    edit_context: Optional[Dict]
    system_prompt: str
    full_prompt: str
    progress_callbacks: List
    generated_code: str
    packages_to_install: List[str]
    components_count: int
    files: List[Dict]
    explanation: str
    warnings: List[str]

# -------------------------------------------------------------------
# Enhanced LLM getters with better error handling
# -------------------------------------------------------------------
def get_openai():
    return ChatOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.2,
        max_tokens=12000,
        streaming=True,
        model="gpt-5",
    )

def get_anthropic():
    return ChatAnthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
        temperature=0.7,
        max_tokens=8192,
        streaming=True,
        model="claude-3-5-sonnet-20240620",
    )

def get_google():
    return ChatGoogleGenerativeAI(
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.7,
        max_tokens=8192,
        streaming=True,
        model="gemini-1.5-pro",
    )

def get_groq():
    return ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.7,
        max_tokens=8192,
        streaming=True,
        model="moonshotai/kimi-k2-instruct",
    )

# Enhanced model selection
def select_model(model_str: str):
    """Enhanced model selection with better fallbacks"""
    try:
        model_lower = model_str.lower()
        if "anthropic" in model_lower or "claude" in model_lower:
            return get_anthropic()
        elif "openai" in model_lower or "gpt" in model_lower:
            return get_openai()
        elif "google" in model_lower or "gemini" in model_lower:
            return get_google()
        elif "groq" in model_lower or "kimi-k2-instruct" in model_lower:
            return get_groq()
        else:
            # Default fallback
            return get_openai()
    except Exception as e:
        print(f"[model_select] Error selecting model {model_str}: {e}")
        return get_openai()  # Safe fallback

# -------------------------------------------------------------------
# Enhanced utility functions
# -------------------------------------------------------------------
def analyze_user_preferences(messages: List[Dict[str, Any]]) -> Dict:
    user_messages = [m for m in messages if m.get("role") == "user"]
    patterns = []
    targeted_edit_count = 0
    comprehensive_edit_count = 0

    for msg in user_messages:
        content = (msg.get("content") or "").lower()

        if re.search(r"\b(update|change|fix|modify|edit|remove|delete)\s+(\w+\s+)?(\w+)\b", content):
            targeted_edit_count += 1

        if re.search(r"\b(rebuild|recreate|redesign|overhaul|refactor)\b", content):
            comprehensive_edit_count += 1

        # Pattern detection
        if "hero" in content:
            patterns.append("hero section edits")
        if "header" in content:
            patterns.append("header modifications")
        if "color" in content or "style" in content:
            patterns.append("styling changes")
        if "button" in content:
            patterns.append("button updates")
        if "animation" in content:
            patterns.append("animation requests")

    return {
        "common_patterns": list(set(patterns))[:3],
        "preferred_edit_style": "targeted" if targeted_edit_count > comprehensive_edit_count else "comprehensive",
    }

def send_progress(callbacks, data):
    """Enhanced progress sending with error handling"""
    for cb in callbacks:
        try:
            if asyncio.iscoroutinefunction(cb):
                asyncio.create_task(cb(data))
            else:
                cb(data)
        except Exception as e:
            print(f"[progress] Error sending progress: {e}")

# -------------------------------------------------------------------


def analyze_intent_node(state: AgentState) -> AgentState:
    """Enhanced intent analysis with redesign detection and logging"""
    prompt = state["prompt"]
    is_edit = state["is_edit"]
    
    print(f"[analyze_intent] Starting intent analysis...")
    print(f"[analyze_intent] Input prompt: '{prompt[:100]}...'")
    print(f"[analyze_intent] Initial is_edit flag: {is_edit}")
    
    # FIXED: Handle redesign requests with synchronous cleanup
    if is_redesign_request(prompt):
        print("[analyze_intent] Redesign request detected - clearing cache and marking for file cleanup")
        
        # Use synchronous cache clearing only
        clear_cache()
        is_edit = False
        state["is_edit"] = False
        state["needs_file_cleanup"] = True  # Flag for async cleanup later
        print("[analyze_intent] Converted redesign to new design (is_edit = False)")
    else:
        print("[analyze_intent] No redesign detected - proceeding with original is_edit flag")
        state["needs_file_cleanup"] = False
    
    # Rest of the function remains the same...
    edit_context = None
    manifest = _manifest()
    
    print(f"[analyze_intent] Manifest available: {manifest is not None}")
    
    if is_edit and manifest:
        print("[analyze_intent] Edit mode with manifest - using analyze_edit_intent module")
        try:
            import sys
            main_app = sys.modules.get("main")
            if main_app and hasattr(main_app, "MODULES"):
                analyze_module = main_app.MODULES.get("analyze_edit_intent")
                if analyze_module:
                    print("[analyze_intent] Found analyze_edit_intent module, calling POST")
                    result = analyze_module.POST({
                        'prompt': prompt,
                        'manifest': manifest,
                        'model': state["model"],
                        
                    })
                    if result.get('success'):
                        edit_context = result.get('editContext')
                        print(f"[analyze_intent] Successfully got edit context from module")
                    else:
                        print(f"[analyze_intent] Module returned failure: {result.get('error', 'Unknown error')}")
                else:
                    print("[analyze_intent] analyze_edit_intent module not found in MODULES")
            else:
                print("[analyze_intent] main_app or MODULES not available")
        except Exception as e:
            print(f"[analyze_intent] ERROR using analysis module: {e}")
    else:
        if not is_edit:
            print("[analyze_intent] New design mode - will use schema")
        else:
            print("[analyze_intent] Edit mode but no manifest available")
    
    state["edit_context"] = edit_context
    print(f"[analyze_intent] Final edit_context set: {edit_context is not None}")
    return state
# -------------------------------------------------------------------
# EXACT TS SYSTEM PROMPT IMPLEMENTATION
# -------------------------------------------------------------------
from pathlib import Path

_UI_GUIDELINES_PATH = Path("/UI_design.md")

def _load_ui_guidelines_text() -> str:
    try:
        if _UI_GUIDELINES_PATH.exists():
            txt = _UI_GUIDELINES_PATH.read_text(encoding="utf-8", errors="ignore")
            return txt.strip()
    except Exception as _e:
        pass
    # Fallback: keep it light if missing
    return "Adhere to clean layout grids, accessible color contrast (>=4.5:1), consistent spacing, responsive breakpoints, readable typography (>=16px), clear CTAs, and subtle motion (200–300ms)."

def build_comprehensive_system_prompt(
    conversation_context: str = "",
    is_edit: bool = False,
    edit_context: Optional[Dict] = None
) -> str:
    ui_rules = _load_ui_guidelines_text()
    schema_section = ""

    if not is_edit:
        print("[build_prompts] New design detected - getting schema")
        schema = get_random_schema() # Your existing function
        if schema:
            schema_section = f"""
DESIGN SCHEMA REQUIREMENTS - FOLLOW EXACTLY:
{json.dumps(schema, indent=2)}

CRITICAL: You must design the website precisely according to this JSON schema. The schema dictates layout, components, colors, and typography. It overrides any other design choices.
"""

    # This new checklist is the most important change.
    enhanced_verification_checklist = """
🚨 MANDATORY PRE-GENERATION CHECKLIST - YOU MUST COMPLETE THIS BEFORE WRITING ANY CODE:

STEP 1: COMPONENT INVENTORY
Mentally create an exact list of every single component file you will generate.
Example: [App.jsx, index.css, Header.jsx, Hero.jsx, Footer.jsx]

STEP 2: IMPORT-COMPONENT MATCHING (THE MOST CRITICAL RULE)
Count the components from Step 1 (excluding App.jsx and index.css). If you have 3 components (Header, Hero, Footer), then your App.jsx MUST import EXACTLY 3 components.
- `import Header from './components/Header'`
- `import Hero from './components/Hero'`
- `import Footer from './components/Footer'`
The number of component imports in App.jsx MUST EXACTLY MATCH the number of component files you generate. NO EXCEPTIONS.

STEP 3: SYNTAX PRE-CHECK
Before writing each file, mentally confirm you will:
- Use straight quotes `"` and `'`, NEVER smart quotes `“` `”` `‘` `’`.
- Close every JSX tag (`<Component />` or `<Component></Component>`).
- Add `import React from 'react'` to every `.jsx` file.
- Add `export default ComponentName` to every component file.

STEP 4: TAILWIND CSS CLASS VALIDATION
- You MUST use ONLY standard Tailwind CSS classes found in the official documentation.
- ✅ CORRECT: `bg-white`, `text-blue-500`, `border-gray-200`
- ❌ FORBIDDEN: `bg-background`, `text-foreground`, `border-border`. These classes DO NOT EXIST and will cause build errors. Do not invent classes.

🛑 CHECKPOINT: If your plan violates any of these steps, you have FAILED and must correct your plan before generating code. VIOLATION = GUARANTEED FAILURE.
"""

    # The main system prompt, now including the new rules.
    system_prompt = f"""You are an expert React developer for Vite applications. Your most important job is to follow instructions perfectly to avoid errors.

{conversation_context}
{schema_section}

{enhanced_verification_checklist}

{ui_rules}

🚨 CRITICAL RULES - YOUR MOST IMPORTANT INSTRUCTIONS:

1.  **FILE COMPLETENESS**: Generate ALL files in FULL. Never use `...` or truncate code. Every file must be a complete, runnable piece of code.
2.  **IMPORT-COMPONENT MATCHING**: This is the #1 rule. If `App.jsx` imports `Header`, `Hero`, and `Footer`, you MUST generate `Header.jsx`, `Hero.jsx`, and `Footer.jsx`. No missing files. No extra files. The Vite error "Failed to resolve import" is a direct result of you failing this rule.
3.  **STANDARD TAILWIND ONLY**: You MUST NOT use placeholder class names like `bg-background`, `text-foreground`, or `border-border`. These cause CSS build errors. Use standard Tailwind classes like `bg-gray-900`, `text-white`, `border-slate-800`.
4.  **SYNTAX PERFECTION**: Always use straight quotes (`"`, `'`). Smart quotes (`“`, `’`) are forbidden and will break the JSX parser. Ensure every tag, bracket, and parenthesis is correctly closed.
5.  **NO CONFIG FILES**: NEVER generate `tailwind.config.js`, `vite.config.js`, or `package.json`. They already exist and are correctly configured.

🚨 CRITICAL OUTPUT FORMAT - USE THIS EXACT XML FORMAT:

<file path="src/index.css">
@tailwind base;
@tailwind components;
@tailwind utilities;
</file>

<file path="src/App.jsx">
import React from 'react';
import Header from './components/Header';
// ... other imports
function App() {{
  return (
    <div>
      <Header />
      {{/* ... other components */}}
    </div>
  );
}}
export default App;
</file>

<file path="src/components/Header.jsx">
import React from 'react';

function Header() {{
  return (
    <header>
      {{/* JSX content */}}
    </header>
  );
}}
export default Header;
</file>

"""

    # Add specific instructions for edit mode
    if is_edit and edit_context:
        system_prompt += f"""
🚨 TARGETED EDIT MODE ACTIVE - BE PRECISE!

You are editing an existing application. DO NOT regenerate the whole app.
- **Files to Edit**: {', '.join(edit_context.get('primaryFiles', []))}
- **Your Task**: ONLY generate the complete, updated content for the files listed above.
- **Preserve Everything**: Do not remove or alter code that is unrelated to the user's request.
- **Rule**: If "Files to Edit" lists ONE file, you generate ONLY THAT ONE FILE. Do not add "helpful" edits to other files.
"""

    return system_prompt
# -------------------------------------------------------------------
# Enhanced prompt building with COMPREHENSIVE SYSTEM PROMPT
# -------------------------------------------------------------------
# Fixed build_prompts_node in generate_ai_stream.py

# Fixed build_prompts_node in generate_ai_stream.py

# Fixed build_prompts_node in generate_ai_stream.py

# routes/generate_ai_stream.py - FIXED with robust file parsing and EXACT TS PROMPTS

# ... (keep all existing imports and helper functions at the top of the file) ...

# ... (include the fixed analyze_intent_node from above) ...

# ... (keep the build_comprehensive_system_prompt function) ...

# -------------------------------------------------------------------
# Enhanced prompt building with COMPREHENSIVE SYSTEM PROMPT
# -------------------------------------------------------------------
# Fixed build_prompts_node in generate_ai_stream.py

# Enhanced build_prompts_node function for generate_ai_stream.py

def build_prompts_node(state: AgentState) -> AgentState:
    """Enhanced prompt building with comprehensive file context for edits"""
    global conversation_state

    prompt = state["prompt"]
    is_edit = state["is_edit"]
    context = state["context"]
    edit_context = state.get("edit_context")

    print(f'[build_prompts_node] 🚀 Building prompts - is_edit: {is_edit}')
    print(f'[build_prompts_node] 📄 Edit context available: {edit_context is not None}')

    # Build conversation context
    conversation_context = ""
    if conversation_state and len(conversation_state.context["messages"]) > 1:
        conversation_context = "\n\n## Conversation History\n"
        recent_edits = conversation_state.context["edits"][-3:]
        if recent_edits:
            conversation_context += "\n### Recent Edits:\n"
            for edit in recent_edits:
                target_files = [f.split("/")[-1] for f in edit["target_files"]]
                conversation_context += f'- "{edit["user_request"]}" → {edit["edit_type"]} ({", ".join(target_files)})\n'

    # Get files map for context
    files_map = _files_map()
    print(f'[build_prompts_node] 📊 Available files in cache: {len(files_map)}')
    
    # BUILD SYSTEM PROMPT - CRITICAL FOR CONTENT PRESERVATION
    if is_edit and edit_context:
        print('[build_prompts_node] 🎯 Using enhanced edit mode prompt with content preservation')
        
        # Create enhanced edit system prompt
        primary_files = edit_context.get("primaryFiles", [])
        # Add critical XML format enforcement for edits
        # primary_files = edit_context.get("primaryFiles", [])
        system_prompt = f"""

🚨 CRITICAL XML FORMAT REQUIREMENT FOR EDITS:

You MUST generate exactly {len(primary_files)} files using this EXACT XML format:

<file path="src/App.jsx">
[complete App.jsx content with gradient theme]
</file>

<file path="src/components/Header.jsx">
[complete Header.jsx content with gradient theme]
</file>

<file path="src/components/Hero.jsx">
[complete Hero.jsx content with gradient theme]
</file>

DO NOT use any other format. DO NOT generate a single large component.
Generate {len(primary_files)} separate <file> blocks, one for each file listed above.

VIOLATION OF THIS FORMAT WILL RESULT IN FAILURE.
"""
        preserve_existing = edit_context.get("preserveExisting", True)
        user_request = edit_context.get("userRequest", prompt)
        
        system_prompt += f"""🚨 CRITICAL EDIT MODE - PRESERVE ALL EXISTING CONTENT

You are editing an existing React application. You MUST preserve all existing content, text, and functionality.

USER REQUEST: "{user_request}"

🔧 EDIT RULES - VIOLATION = COMPLETE FAILURE:
1. **PRESERVE ALL EXISTING TEXT CONTENT** - Do not change any text, headings, descriptions, or copy
2. **PRESERVE ALL EXISTING FUNCTIONALITY** - Keep all existing components, imports, and logic
3. **PRESERVE COMPONENT STRUCTURE** - Do not reorganize or rename existing components
4. **ONLY MAKE THE REQUESTED CHANGE** - For "change theme to gradient", only update styling/colors

📋 FILES TO EDIT: {len(primary_files)} files
{chr(10).join(f'- {f.split("/")[-1]}' for f in primary_files)}

🎨 FOR STYLING/THEME CHANGES:
- Update Tailwind CSS classes for colors, backgrounds, gradients
- Add smooth transitions and modern effects
- Enhance visual design while keeping all text exactly the same
- Use gradient backgrounds like: bg-gradient-to-r from-blue-600 to-purple-600

❌ FORBIDDEN ACTIONS:
- Changing any text content or copy
- Adding placeholder text like "Welcome to our website"
- Removing existing sections or components
- Changing the website's purpose or message
- Creating entirely new content

✅ ALLOWED ACTIONS:
- Updating CSS classes for styling
- Adding gradient backgrounds
- Improving visual design
- Enhancing color schemes
- Adding hover effects and transitions

{conversation_context}

CRITICAL: You will be provided with the EXACT existing file content below. You must preserve this content and only make the styling changes requested."""

    else:
        print('[build_prompts_node] 📝 Using standard prompt')
        system_prompt = build_comprehensive_system_prompt(conversation_context, is_edit, edit_context)

    # BUILD FULL PROMPT WITH EXISTING FILE CONTENT
    full_prompt = prompt

    if context:
        parts = []

        if context.get("sandboxId"):
            parts.append(f"Sandbox ID: {context['sandboxId']}")

        # 🚨 CRITICAL: Include existing file content for edit mode
        if is_edit and edit_context and files_map:
            print(f'[build_prompts_node] 📁 Including existing file content for {len(edit_context.get("primaryFiles", []))} files')
            
            primary_files = edit_context.get("primaryFiles", [])
            existing_content = edit_context.get("existingContent", {})
            
            if primary_files:
                parts.append("\n🚨 EXISTING FILES - PRESERVE ALL CONTENT:")
                
                for file_path in primary_files:
                    file_name = file_path.split("/")[-1]
                    relative_path = file_path.replace("/home/user/app/", "")
                    
                    # Get content from edit context or files_map
                    content = existing_content.get(file_path) or files_map.get(file_path, {}).get("content", "")
                    
                    if content:
                        parts.append(f'\n<existing_file path="{relative_path}" name="{file_name}">')
                        parts.append(f'CURRENT CONTENT ({len(content)} chars) - PRESERVE ALL TEXT:')
                        parts.append('```jsx')
                        parts.append(content)
                        parts.append('```')
                        parts.append('</existing_file>')
                        
                        print(f'[build_prompts_node] ✅ Included existing content: {file_name} ({len(content)} chars)')
                    else:
                        print(f'[build_prompts_node] ⚠️ No content found for: {file_name}')

                # Add critical preservation instructions
                parts.append(f'\n🎯 EDIT INSTRUCTIONS:')
                parts.append(f'- Request: "{prompt}"')
                parts.append(f'- Preserve: ALL existing text content and functionality')
                parts.append(f'- Target: ONLY the files listed above')
                parts.append(f'- Do NOT: Add new components or change App.jsx imports')
                parts.append(f'- CRITICAL: For style/theme changes, NEVER include App.jsx in your output')
                parts.append(f'- CRITICAL: Only output the files that were provided in the existing content above')

        # Add conversation context
        if conversation_context:
            parts.append(f"\n📝 CONVERSATION CONTEXT:\n{conversation_context}")

        if parts:
            full_prompt = f"{full_prompt}\n\n{' '.join(parts)}"

    state["system_prompt"] = system_prompt
    state["full_prompt"] = full_prompt

    print(f'[build_prompts_node] 📏 System prompt length: {len(system_prompt)}')
    print(f'[build_prompts_node] 📏 Full prompt length: {len(full_prompt)}')

    send_progress(state["progress_callbacks"], {"type": "status", "message": "🧠 Building enhanced generation prompts with file context..."})
    
    if is_edit and edit_context:
        primary_files_count = len(edit_context.get('primaryFiles', []))
        send_progress(state["progress_callbacks"], {
            "type": "status", 
            "message": f"🔧 Edit mode: targeting {primary_files_count} files with existing content preserved"
        })
    
    return state


def build_enhanced_edit_prompt(edit_context: Dict, conversation_context: str = "") -> str:
    """Build comprehensive edit prompt that preserves existing content"""
    
    edit_type = edit_context.get("editType", "UPDATE_COMPONENT")
    primary_files = edit_context.get("primaryFiles", [])
    preserve_existing = edit_context.get("preserveExisting", True)
    enhance_only = edit_context.get("enhanceOnly", False)
    target_sections = edit_context.get("targetSections", [])
    
    system_prompt = f"""🚨 CRITICAL EDIT MODE - PRESERVE EXISTING WEBSITE STRUCTURE

{edit_context.get('systemPrompt', '')}

{conversation_context}

🔧 EDIT CONTEXT ANALYSIS:
- Edit Type: {edit_type}
- Target Files: {len(primary_files)} files
- Preserve Content: {preserve_existing}
- Enhance Only: {enhance_only}
- Target Sections: {target_sections}

🗂️ FILES TO MODIFY:
{chr(10).join(f'- {f.split("/")[-1]}' for f in primary_files)}

🚨 CRITICAL EDIT RULES - VIOLATION = COMPLETE FAILURE:

1. **PRESERVE EXISTING WEBSITE IDENTITY**
   - Keep ALL existing text content exactly as is
   - Maintain ALL existing functionality and component structure
   - Do NOT add placeholder text or dummy content
   - Do NOT change the website's purpose or message

2. **ENHANCE ONLY THE VISUAL DESIGN** (if enhance_only={enhance_only})
   - Improve typography, colors, spacing, and layout
   - Add professional Tailwind CSS classes
   - Include smooth transitions and hover effects
   - Upgrade to modern UI patterns
   - Make responsive design improvements

3. **MAINTAIN COMPONENT STRUCTURE**
   - Do NOT reorganize or rename existing components
   - Do NOT merge or split existing components
   - Do NOT change imports or component relationships
   - Keep all existing component functionality

4. **CRITICAL OUTPUT REQUIREMENTS**
   - Generate ONLY the {len(primary_files)} files specified above
   - Include ALL existing content in each file
   - Make ONLY the requested changes
   - Ensure all files are complete and functional

5. **FORBIDDEN ACTIONS**
   - ❌ Do NOT create new components unless specifically requested
   - ❌ Do NOT add new sections not mentioned in the request
   - ❌ Do NOT change existing text content (unless specifically asked)
   - ❌ Do NOT remove existing features or functionality
   - ❌ Do NOT create duplicate components

6. **FILE COMPLETION REQUIREMENTS**
   - Every file must include ALL imports at the top
   - Every file must include ALL existing functions and content
   - Every file must have proper closing tags and exports
   - Every file must be complete and runnable

EXAMPLE OF CORRECT ENHANCEMENT:
❌ WRONG: Changing "About Our Company" to "About Us"  
✅ CORRECT: Keeping "About Our Company" but styling it with: text-4xl font-bold text-gray-900

❌ WRONG: Adding new testimonials section
✅ CORRECT: Enhancing existing testimonials with better CSS classes

❌ WRONG: Reorganizing page layout completely
✅ CORRECT: Improving spacing and visual hierarchy of existing layout

CRITICAL SUCCESS CRITERIA:
- User will see their existing website with improved styling
- NO content should be lost or changed unexpectedly
- ALL existing functionality should continue to work
- The website should look more professional while keeping its identity"""

    return system_prompt
# -------------------------------------------------------------------
# 🚨 FIXED FILE PARSING - ROBUST AND COMPREHENSIVE
# -------------------------------------------------------------------
def validate_jsx_syntax(content: str, file_path: str) -> str:
    """Validate and fix common JSX syntax issues"""
    
    # Fix smart quotes in className and other JSX attributes
    content = re.sub(r'className="([^"]*)"', lambda m: f'className="{m.group(1)}"', content)
    # content = re.sub(r'className='([^']*)'', lambda m: f"className='{m.group(1)}'", content)
    
    # Ensure React import exists for JSX files
    if file_path.endswith('.jsx') and 'import React' not in content:
        if 'import' in content:
            # Add React import after existing imports
            content = re.sub(r'(import[^;]+;)', r'\1\nimport React from "react"', content, count=1)
        else:
            # Add React import at the beginning
            content = 'import React from "react"\n\n' + content
    
    # Ensure default export exists for JSX files
    if file_path.endswith('.jsx') and 'export default' not in content:
        # Try to find function name and add export
        func_match = re.search(r'function\s+(\w+)', content)
        if func_match:
            func_name = func_match.group(1)
            if f'export default {func_name}' not in content:
                content += f'\n\nexport default {func_name}'
    
    return content

def parse_files_from_content(content: str) -> List[Dict[str, str]]:
    """ENHANCED: Robust file parser with validation and completeness checks"""
    
    content = sanitize_content_for_utf8(content)
    files: List[Dict[str, str]] = []
    
    print(f"[parse_files] Analyzing {len(content)} characters")
    
    # Strategy 1: Standard XML format with completeness validation
    xml_pattern = r'<file\s+path="([^"]+)">(.*?)</file>'
    xml_matches = re.findall(xml_pattern, content, re.DOTALL)
    
    if xml_matches:
        print(f"[parse_files] Found {len(xml_matches)} XML files")
        for path, file_content in xml_matches:
            cleaned_content = sanitize_content_for_utf8(file_content.strip())
            
            # CRITICAL: Validate file completeness
            if not cleaned_content:
                print(f"[parse_files] ERROR: Empty content for {path}")
                continue
                
            # Validate JSX files have proper structure
            if path.endswith(('.jsx', '.tsx')):
                validation_result = validate_jsx_completeness(cleaned_content, path)
                if not validation_result['valid']:
                    print(f"[parse_files] ERROR: Invalid JSX structure in {path}: {validation_result['errors']}")
                    # Try to fix the JSX
                    cleaned_content = fix_jsx_structure(cleaned_content, path)
                    
            cleaned_content = validate_jsx_syntax(cleaned_content, path)
            files.append({"path": path, "content": cleaned_content})
            print(f"[parse_files] ✅ Validated: {path} ({len(cleaned_content)} chars)")
            
        # CRITICAL: Validate App.jsx imports match generated components
        app_jsx_file = next((f for f in files if f['path'].endswith('App.jsx')), None)
        if app_jsx_file:
            validation_errors = validate_app_imports(app_jsx_file, files)
            if validation_errors:
                print(f"[parse_files] ERROR: App.jsx validation failed: {validation_errors}")
                # Fix the App.jsx imports
                app_jsx_file['content'] = fix_app_imports(app_jsx_file['content'], files)
                print("[parse_files] ✅ Fixed App.jsx imports")
                
        return files
    
    # Fallback strategies remain the same but with validation
    print("[parse_files] No valid XML files found")
    return []

def validate_jsx_completeness(content: str, file_path: str) -> Dict[str, Any]:
    """Validate that JSX file is complete and properly structured"""
    errors = []
    
    # Check for basic JSX structure
    if not re.search(r'function\s+\w+|const\s+\w+\s*=', content):
        errors.append("Missing function/component declaration")
    
    if not 'export default' in content:
        errors.append("Missing export default statement")
    
    # Check for unclosed tags/brackets
    open_braces = content.count('{')
    close_braces = content.count('}')
    if open_braces != close_braces:
        errors.append(f"Mismatched braces: {open_braces} open, {close_braces} close")
    
    open_parens = content.count('(')
    close_parens = content.count(')')
    if open_parens != close_parens:
        errors.append(f"Mismatched parentheses: {open_parens} open, {close_parens} close")
    
    # Check for JSX tag completeness
    jsx_tag_pattern = r'<(\w+)[^>]*>'
    jsx_close_pattern = r'</(\w+)>'
    
    open_tags = re.findall(jsx_tag_pattern, content)
    close_tags = re.findall(jsx_close_pattern, content)
    
    # Filter out self-closing tags
    self_closing = re.findall(r'<(\w+)[^>]*/>', content)
    
    # Remove self-closing tags from open_tags count
    for tag in self_closing:
        if tag in open_tags:
            open_tags.remove(tag)
    
    unmatched_tags = set(open_tags) - set(close_tags)
    if unmatched_tags:
        errors.append(f"Unclosed JSX tags: {list(unmatched_tags)}")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }

def fix_jsx_structure(content: str, file_path: str) -> str:
    """Fix common JSX structure issues"""
    
    # Ensure React import
    if 'import React' not in content and file_path.endswith('.jsx'):
        content = "import React from 'react'\n\n" + content
    
    # Fix missing export default
    if 'export default' not in content:
        # Find the component name
        func_match = re.search(r'(?:function|const)\s+(\w+)', content)
        if func_match:
            component_name = func_match.group(1)
            content += f'\n\nexport default {component_name}'
    
    # Fix common syntax issues
    content = re.sub(r'className=\{([^}]+)\}', r'className={\1}', content)
    
    return content

def validate_app_imports(app_file: Dict[str, str], all_files: List[Dict[str, str]]) -> List[str]:
    """Validate that App.jsx imports match the generated component files"""
    errors = []
    app_content = app_file['content']
    
    # Extract imports from App.jsx
    import_pattern = r'import\s+(\w+)\s+from\s+[\'"]\.\/components\/(\w+)[\'"]'
    imports = re.findall(import_pattern, app_content)
    
    # Extract component usage in JSX
    jsx_usage_pattern = r'<(\w+)\s*[^>]*/?>'
    used_components = set(re.findall(jsx_usage_pattern, app_content))
    
    # Get list of generated component files
    component_files = [f for f in all_files if 'components/' in f['path'] and f['path'].endswith(('.jsx', '.tsx'))]
    component_names = [f['path'].split('/')[-1].replace('.jsx', '').replace('.tsx', '') for f in component_files]
    
    # Check for imported but not generated components
    for import_name, file_name in imports:
        if file_name not in component_names:
            errors.append(f"Imported {import_name} but {file_name}.jsx not generated")
    
    # Check for used but not imported components
    for component in used_components:
        if component in component_names and not any(imp[0] == component for imp in imports):
            errors.append(f"Component {component} used but not imported")
    
    return errors

def fix_app_imports(app_content: str, all_files: List[Dict[str, str]]) -> str:
    """Fix App.jsx imports to match generated components"""
    
    # Get list of generated component files
    component_files = [f for f in all_files if 'components/' in f['path'] and f['path'].endswith(('.jsx', '.tsx'))]
    component_names = [f['path'].split('/')[-1].replace('.jsx', '').replace('.tsx', '') for f in component_files]
    
    # Extract current imports
    import_section = []
    other_imports = []
    
    lines = app_content.split('\n')
    for line in lines:
        if line.strip().startswith('import') and not './components/' in line:
            other_imports.append(line)
        elif not line.strip().startswith('import'):
            break
    
    # Build correct component imports
    for component_name in component_names:
        import_line = f"import {component_name} from './components/{component_name}'"
        import_section.append(import_line)
    
    # Rebuild the file
    all_imports = other_imports + import_section
    
    # Find where imports end
    import_end_index = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('import'):
            import_end_index = i + 1
        elif line.strip() and not line.strip().startswith('import'):
            break
    
    # Rebuild content
    new_content = '\n'.join(all_imports) + '\n\n' + '\n'.join(lines[import_end_index:])
    
    return new_content

# -------------------------------------------------------------------
# Enhanced code generation node with FIXED PARSING
# -------------------------------------------------------------------
def code_generation_node(state: AgentState) -> AgentState:
    packages_to_install: List[str] = []
    files: List[Dict[str, str]] = []
    component_count = 0
    generated_code = ""

    try:
        model_name = state["model"]
        print(f"[code_generation] 🚀 Using model: {model_name}")

        # Enhanced model selection
        llm = select_model(model_name)

        # Enhanced streaming setup
        generation_prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            ("human", "{full_prompt}"),
        ])

        chain = generation_prompt | llm | StrOutputParser()

        # Enhanced streaming with FIXED file parsing
        buffer: List[str] = []
        current_file_content: List[str] = []
        in_file = False
        current_file_path = ""
        chunk_count = 0

        print("[code_generation] 🔄 Starting enhanced streaming with FIXED parsing...")

        try:
            files, generated_code, syntax_errors = enhanced_streaming_with_validation(chain, state)
            
            if syntax_errors:
                print(f"[code_generation] Syntax errors found: {syntax_errors}")
                state["warnings"].extend(syntax_errors)

        except Exception as e:
            print(f"[code_generation] ⚠️  Streaming error: {e}")

        print(f"[code_generation] 📊 Streaming complete: {len(generated_code)} chars, {len(files)} files from real-time parsing")

        # 🚨 CRITICAL: Use FIXED fallback parsing if no files found during streaming
        if not files:
            print("[code_generation] 🔧 No files from streaming, using FIXED fallback parser...")
            files = parse_files_from_content(generated_code)
            component_count = sum(1 for f in files if "components/" in f["path"])
            print(f"[code_generation] 🔧 Fallback parser found: {len(files)} files")

        # Extract packages from file contents
        for file in files:
            content = file["content"]
            import_pattern = r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]'
            for match in re.finditer(import_pattern, content):
                import_path = match.group(1)
                if (
                    not import_path.startswith((".", "/", "@/"))
                    and import_path not in ("react", "react-dom")
                ):
                    pkg_name = import_path.split("/")[0]
                    if import_path.startswith("@"):
                        pkg_name = "/".join(import_path.split("/")[:2])
                    if pkg_name not in packages_to_install:
                        packages_to_install.append(pkg_name)

        # Extract explanation
        explanation_match = re.search(r"<explanation>(.*?)</explanation>", generated_code, re.DOTALL)
        explanation = explanation_match.group(1).strip() if explanation_match else "Code generated successfully with enhanced parsing!"

        # Parse package tags
        for pkg_match in re.finditer(r"<package>([^<]+)</package>", generated_code):
            pkg = pkg_match.group(1).strip()
            if pkg and pkg not in packages_to_install:
                packages_to_install.append(pkg)

        print(f"[code_generation] 🎯 FINAL RESULT: {len(files)} files, {len(packages_to_install)} packages")
        for f in files:
            print(f"[code_generation]   ✅ {f['path']} ({len(f['content'])} chars)")

        # PASTE THIS NEW BLOCK IN ITS PLACE:

        print("[code_generation] 🔬 Applying comprehensive validation and self-correction...")
        validation_result = validate_and_correct_code(files)  # Use the new function

        state["files"] = validation_result["files"]  # Use the corrected list of files
        state["warnings"].extend(validation_result["warnings"])
        state["errors"] = validation_result["errors"]

        if not validation_result["valid"]:
            print(f"[code_generation] ❌ Validation failed: {validation_result['errors']}")
        else:
            print("[code_generation] ✅ Validation and self-correction passed.")
                
        if validation_result['warnings']:
            print(f"[code_generation] ⚠️ Warnings: {validation_result['warnings']}")
            state["warnings"].extend(validation_result['warnings'])
        send_progress(state["progress_callbacks"], {
            "type": "complete",
            "generated_code": generated_code,
            "explanation": explanation,
            "files": len(files),
            "components": component_count,
            "model": state["model"],
            "packages_to_install": packages_to_install,
        })

        state["generated_code"] = generated_code
        state["files"] = files
        state["packages_to_install"] = packages_to_install
        state["components_count"] = component_count
        state["explanation"] = explanation
        state["warnings"] = []

    except Exception as e:
        print(f"[code_generation] ❌ Error: {e}")
        state["generated_code"] = ""
        state["files"] = []
        state["packages_to_install"] = []
        state["components_count"] = 0
        state["explanation"] = f"Generation failed: {str(e)}"
        state["warnings"] = [str(e)]

    return state
# Replace the streaming section in code_generation_node with this enhanced version:

def enhanced_streaming_with_validation(chain, state):
    """Enhanced streaming with real-time syntax validation"""
    
    buffer = []
    files = []
    current_file_content = []
    in_file = False
    current_file_path = ""
    syntax_errors = []
    
    for chunk in chain.stream({
        "system_prompt": state["system_prompt"],
        "full_prompt": state["full_prompt"]
    }):
        buffer.append(chunk)
        
        # Real-time file detection
        if '<file path="' in chunk and not in_file:
            in_file = True
            current_file_content = [chunk]
            path_match = re.search(r'<file path="([^"]+)"', chunk)
            if path_match:
                current_file_path = path_match.group(1)
                print(f"[streaming] Starting file: {current_file_path}")
                
        elif in_file:
            current_file_content.append(chunk)
            
            # Check for file completion
            if "</file>" in chunk:
                full_file_content = "".join(current_file_content)
                file_match = re.search(r'<file path="([^"]+)">(.*?)</file>', full_file_content, re.DOTALL)
                
                if file_match:
                    path, content = file_match.groups()
                    cleaned_content = sanitize_content_for_utf8(content.strip())
                    
                    # REAL-TIME SYNTAX VALIDATION
                    try:
    # REAL-TIME SYNTAX VALIDATION
                        if path.endswith(('.jsx', '.tsx')):
                            syntax_check = check_jsx_syntax_realtime(cleaned_content, path)
                            if not syntax_check['valid']:
                                print(f"[streaming] SYNTAX ERROR in {path}: {syntax_check['errors']}")
                                syntax_errors.extend(syntax_check['errors'])
                                # Try to fix syntax issues
                                cleaned_content = fix_syntax_errors(cleaned_content, syntax_check['errors'])
                                # Re-validate after fix
                                recheck = check_jsx_syntax_realtime(cleaned_content, path)
                                if recheck['valid']:
                                    print(f"[streaming] ✅ Fixed syntax errors in {path}")
                    except Exception as e:
                        print(f"[streaming] Error in syntax validation for {path}: {e}")
                
                in_file = False
                current_file_content = []
                current_file_path = ""
        
        # Send progress
        send_progress(state["progress_callbacks"], {
            "type": "stream",
            "text": chunk,
            "raw": True
        })
    
    return files, "".join(buffer), syntax_errors

def check_jsx_syntax_realtime(content: str, file_path: str) -> Dict[str, Any]:
    """Real-time JSX syntax validation"""
    errors = []
    
    # Check quote balance
    single_quotes = content.count("'") - content.count("\\'")
    double_quotes = content.count('"') - content.count('\\"')
    
    if single_quotes % 2 != 0:
        errors.append("Unmatched single quotes")
    if double_quotes % 2 != 0:
        errors.append("Unmatched double quotes")
    
    # Check brace balance
    open_braces = content.count('{')
    close_braces = content.count('}')
    if open_braces != close_braces:
        errors.append(f"Mismatched braces: {open_braces} open, {close_braces} close")
    
    # Check parentheses balance  
    open_parens = content.count('(')
    close_parens = content.count(')')
    if open_parens != close_parens:
        errors.append(f"Mismatched parentheses: {open_parens} open, {close_parens} close")
    
    # Check for smart quotes
    if '"' in content or '"' in content or ''' in content or ''' in content:
        errors.append("Contains smart quotes - use straight quotes")
    
    # Check for required JSX structure
    if file_path.endswith('.jsx'):
        if not re.search(r'function\s+\w+|const\s+\w+\s*=', content):
            errors.append("Missing component function/const declaration")
        
        if 'export default' not in content:
            errors.append("Missing export default statement")
        
        if not re.search(r'return\s*\(', content):
            errors.append("Missing return statement")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }

def fix_syntax_errors(content: str, errors: List[str]) -> str:
    """Attempt to fix common syntax errors"""
    
    for error in errors:
        if "smart quotes" in error:
            # Fix smart quotes
            content = content.replace('"', '"').replace('"', '"')
            content = content.replace(''', "'").replace(''', "'")
        
        elif "Missing export default" in error:
            # Add export default
            func_match = re.search(r'function\s+(\w+)', content)
            if func_match:
                func_name = func_match.group(1)
                if f'export default {func_name}' not in content:
                    content += f'\n\nexport default {func_name}'
        
        elif "Missing component function" in error:
            # This is harder to fix automatically, but we can try
            if 'function' not in content and 'const' not in content:
                # Try to extract component name from file path
                # This would need more sophisticated logic
                pass
    
    return content
#
# ❗️ In generate_ai_stream.py, DELETE your old `validate_generated_code` and `fix_generation_errors` functions.
#    REPLACE them with this new function:
#

def validate_and_correct_code(files: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Upgraded validation that now performs deep syntax checks and auto-correction.
    """
    print("🔬 [Validation v2] Starting comprehensive code validation with syntax checks...")
    warnings = []
    errors = []

    for i, file_data in enumerate(files):
        path = file_data.get('path', 'unknown_file')
        content = file_data.get('content', '')

        # --- PASS 1: Aggressive Sanitization ---
        sanitized_content = sanitize_content_for_utf8(content)
        if sanitized_content != content:
            warnings.append(f"Sanitized special characters/whitespace in {path}")
            files[i]['content'] = sanitized_content
            content = sanitized_content # Use the sanitized content for further checks

        # --- PASS 2: JSX Syntax Auto-Correction (The key fix for your error) ---
        if path.endswith(".jsx"):
            # Pattern to find template literals `${...}` inside single or double quoted strings
            # This is a common LLM error in classNames
            error_pattern = re.compile(r"""(className=\{)(['"])(.*?\$\{.*?\}.*?)(['"])\}""")
            
            # Use a function to replace the quotes with backticks
            def replacer(match):
                warnings.append(f"Auto-corrected invalid template literal in className for {path}")
                # Reconstruct with backticks
                return f"{match.group(1)}`{match.group(3)}`}}"

            corrected_content, num_replacements = error_pattern.subn(replacer, content)

            if num_replacements > 0:
                print(f"🔧 [Validation v2] Auto-corrected {num_replacements} invalid template literal(s) in {path}")
                files[i]['content'] = corrected_content
                content = corrected_content # Use the corrected content for further checks

    # --- PASS 3: Structural Validation (Imports vs. Files) ---
    app_file_index = next((i for i, f in enumerate(files) if f['path'].endswith('App.jsx')), -1)

    if app_file_index == -1:
        errors.append("Validation failed: No App.jsx file was generated.")
    else:
        app_content = files[app_file_index]['content']
        generated_components = {f['path'].split('/')[-1].replace('.jsx', '') for f in files if 'components/' in f['path']}
        
        import_pattern = re.compile(r'import\s+(\w+)\s+from\s+[\'"]\./components/(\w+)[\'"];?\n?')
        imports_found = import_pattern.findall(app_content)

        for component_name, file_name in imports_found:
            if file_name not in generated_components:
                warning_msg = f"Correction: Removing import for '{component_name}' from App.jsx because '{file_name}.jsx' was NOT generated."
                print(f"🔧 [Validation v2] {warning_msg}")
                warnings.append(warning_msg)
                
                # Remove the import line and its JSX usage
                import_line_pattern = re.compile(r'import\s+{}\s+from\s+[\'"]\./components/{}[\'"];?\n?'.format(re.escape(component_name), re.escape(file_name)))
                app_content = import_line_pattern.sub('', app_content)
                usage_pattern = re.compile(r'<{}\s*/>\n?'.format(re.escape(component_name)))
                app_content = usage_pattern.sub('', app_content)
        
        files[app_file_index]['content'] = app_content

    print("✅ [Validation v2] All checks passed or were corrected.")
    return {'valid': len(errors) == 0, 'files': files, 'errors': errors, 'warnings': warnings}


def fix_generation_errors(files: List[Dict[str, str]], errors: List[str]) -> List[Dict[str, str]]:
    """Attempt to automatically fix common generation errors"""
    
    for error in errors:
        if "missing React import" in error:
            # Find the file and add React import
            file_name = error.split()[0].replace('.jsx', '')
            for file_data in files:
                if file_data['path'].endswith(f'{file_name}.jsx'):
                    if 'import React' not in file_data['content']:
                        file_data['content'] = "import React from 'react'\n\n" + file_data['content']
        
        elif "missing export default" in error:
            # Add missing export default
            match = re.search(r'(\w+)\.jsx missing export default (\w+)', error)
            if match:
                file_name, comp_name = match.groups()
                for file_data in files:
                    if file_data['path'].endswith(f'{file_name}.jsx'):
                        if f'export default {comp_name}' not in file_data['content']:
                            file_data['content'] += f'\n\nexport default {comp_name}'
        
        elif "imports" in error and "not found" in error:
            # Fix missing component files by creating them
            match = re.search(r'imports (\w+) but (\w+)\.jsx not found', error)
            if match:
                comp_name = match.group(1)
                # Create a basic component
                new_component = f'''import React from 'react'

        function {comp_name}() {{
        return (
            <div className="p-4">
            <h2 className="text-xl font-bold">{comp_name} Component</h2>
            <p>This component was auto-generated to fix import error.</p>
            </div>
        )
        }}

        export default {comp_name}'''
                
                files.append({
                    'path': f'src/components/{comp_name}.jsx',
                    'content': new_component
                })
                print(f"[fix_errors] Created missing component: {comp_name}.jsx")
            
    return files
# -------------------------------------------------------------------
# Enhanced public API
# -------------------------------------------------------------------
def generate_code(
    prompt: str,
    model: str = "openai/gpt-5",
    context: Optional[Dict] = None,
    is_edit: bool = False
) -> Dict[str, Any]:
    """Enhanced code generation function"""
    if is_redesign_request(prompt):
        clear_cache()
        is_edit = False
    global conversation_state

    if context is None:
        context = {}

    if conversation_state is None:
        conversation_state = ConversationState()

    # Add message to conversation
    conversation_state.context["messages"].append({
        "id": f"msg-{int(time.time())}",
        "role": "user",
        "content": prompt,
        "timestamp": int(time.time()),
        "metadata": {"sandboxId": context.get("sandboxId")},
    })

    # Enhanced progress tracking
    progress_callbacks = [lambda data: print(f"[gen] {data}")]

    # Initial state
    state: AgentState = AgentState(
        prompt=prompt,
        model=model,
        context=context,
        is_edit=is_edit,
        conversation_history=conversation_state.context["messages"],
        edit_context=None,
        system_prompt="",
        full_prompt="",
        progress_callbacks=progress_callbacks,
        generated_code="",
        packages_to_install=[],
        components_count=0,
        files=[],
        explanation="",
        warnings=[]
    )

    # Enhanced graph construction
    graph = StateGraph(AgentState)

    def entry_condition(s: AgentState) -> str:
        return "analyze_intent" if (s["is_edit"] and _manifest()) else "build_prompts"

    graph.add_node("analyze_intent", analyze_intent_node)
    graph.add_node("build_prompts", build_prompts_node)
    graph.add_node("generate_code", code_generation_node)

    graph.add_conditional_edges(START, entry_condition, {
        "analyze_intent": "analyze_intent",
        "build_prompts": "build_prompts"
    })
    graph.add_edge("analyze_intent", "build_prompts")
    graph.add_edge("build_prompts", "generate_code")
    graph.add_edge("generate_code", END)

    # Execute graph
    agent = graph.compile()
    result = agent.invoke(state)
    if state.get("needs_file_cleanup", False):
        print("[generate_code] Performing physical file cleanup for redesign...")
        try:
            # Use asyncio.run to properly execute the async function
            import asyncio
            asyncio.run(clear_cache_and_files())
            print("[generate_code] File cleanup completed successfully")
        except Exception as e:
            print(f"[generate_code] File cleanup error: {e}")


    return {
        "success": True,
        "generated_code": result["generated_code"],
        "files": result["files"],
        "explanation": result["explanation"],
        "packages_to_install": result["packages_to_install"],
        "components_count": result["components_count"],
    }

async def stream_generate_code(
    prompt: str,
    model: str = "openai/gpt-5",
    context: Optional[Dict] = None,
    is_edit: bool = False
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    An async generator that yields progress events for code generation.
    """
    global conversation_state, sandbox_state
    sandbox_state = get_sandbox_state()
    if context is None:
        context = {}
    if conversation_state is None:
        conversation_state = ConversationState()

    # Add message to conversation
    conversation_state.context["messages"].append({
        "id": f"msg-{int(time.time())}",
        "role": "user",
        "content": prompt,
        "timestamp": int(time.time()),
    })

    # Queue for progress callbacks
    progress_queue: asyncio.Queue = asyncio.Queue()

    def progress_callback(data):
        progress_queue.put_nowait(data)

    initial_state = AgentState(
        prompt=prompt,
        model=model,
        context=context,
        is_edit=is_edit,
        conversation_history=conversation_state.context["messages"],
        progress_callbacks=[progress_callback],
        generated_code="",
        files=[],
        explanation="",
        packages_to_install=[],
        components_count=0,
        warnings=[],
        edit_context=None,
        system_prompt="",
        full_prompt=""
    )

    # Build the graph
    graph = StateGraph(AgentState)

    def entry_condition(s: AgentState) -> str:
        return "analyze_intent" if (s["is_edit"] and _manifest()) else "build_prompts"

    graph.add_node("analyze_intent", analyze_intent_node)
    graph.add_node("build_prompts", build_prompts_node)
    graph.add_node("generate_code", code_generation_node)
    graph.add_conditional_edges(START, entry_condition, {
        "analyze_intent": "analyze_intent",
        "build_prompts": "build_prompts"
    })
    graph.add_edge("analyze_intent", "build_prompts")
    graph.add_edge("build_prompts", "generate_code")
    graph.add_edge("generate_code", END)

    agent = graph.compile()

    # Run the graph in a background task
    async def run_agent():
        try:
            await agent.ainvoke(initial_state)
        finally:
            # Signal completion
            await progress_queue.put(None)

    agent_task = asyncio.create_task(run_agent())

    # Yield progress from the queue
    while True:
        chunk = await progress_queue.get()
        if chunk is None:
            break
        yield chunk

    await agent_task  # Ensure the agent task completes