# routes/generate_ai_stream.py - FIXED with robust file parsing and EXACT TS PROMPTS
from __future__ import annotations

import os
import re
import json
import time
import asyncio
from typing import Dict, List, Optional, TypedDict, Any, AsyncGenerator

from dotenv import load_dotenv

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
                print(f"[schema] Processing row {row_count}")
                
                schema_json = row.get('JSON SCHEMA', '').strip()
                if not schema_json:
                    print(f"[schema] Row {row_count}: Empty JSON SCHEMA field, skipping")
                    continue
                
                try:
                    parsed_schema = json.loads(schema_json)
                    schemas.append(parsed_schema)
                    print(f"[schema] Row {row_count}: Successfully parsed JSON schema")
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
    """
    Sanitize content to remove/fix characters that cause UTF-8 encoding issues
    """
    if not isinstance(content, str):
        return str(content)
    
    # Remove or replace surrogate characters
    content = content.encode('utf-8', errors='replace').decode('utf-8')
    
    # Remove any remaining problematic characters
    content = ''.join(char for char in content if unicodedata.category(char) != 'Cs')
    
    # Replace common problematic characters
    replacements = {
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201C': '"',  # Left double quotation mark
        '\u201D': '"',  # Right double quotation mark
        '\u2013': '-',  # En dash
        '\u2014': '--', # Em dash
        '\u2026': '...', # Horizontal ellipsis
        '\u00A0': ' ',  # Non-breaking space
    }
    
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    # Remove any remaining non-printable characters except newlines and tabs
    content = re.sub(r'[^\x20-\x7E\n\t]', '', content)
    
    return content

# Enhanced file cache access
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
        temperature=0.7,
        max_tokens=8192,
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
                        'manifest': manifest
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
    print(f"[build_prompts] UI rules loaded: {len(ui_rules)} characters")
    schema_section = ""
    if not is_edit:
        print("[build_prompts] New design detected - getting schema")
        schema = get_random_schema()
        if schema:
            schema_section = f"""
DESIGN SCHEMA REQUIREMENTS - FOLLOW EXACTLY:
{json.dumps(schema, indent=2)}

CRITICAL: Design the website according to this JSON schema structure. The schema defines:
- Layout hierarchy and component structure
- Color schemes and visual styling
- Typography and spacing requirements  
- Interactive elements and sections
- Content organization patterns

Apply UI Design Principles WITHIN the schema constraints. Schema requirements override default choices.
"""
    # Start with the exact TS system prompt
    system_prompt = f"""You are an expert React developer with perfect memory of the conversation. You maintain context across messages and remember scraped websites, generated components, and applied code. Generate clean, modern React code for Vite applications.
{conversation_context}

{schema_section}

{ui_rules}

🚨 CRITICAL RULES - YOUR MOST IMPORTANT INSTRUCTIONS:
1. **DO EXACTLY WHAT IS ASKED - NOTHING MORE, NOTHING LESS**
   - Don't add features not requested
   - Don't fix unrelated issues
   - Don't improve things not mentioned
2. **CHECK App.jsx FIRST** - ALWAYS see what components exist before creating new ones
3. **NAVIGATION LIVES IN Header.jsx** - Don't create Nav.jsx if Header exists with nav
4. **USE STANDARD TAILWIND CLASSES ONLY**:
   - ✅ CORRECT: bg-white, text-black, bg-blue-500, bg-gray-100, text-gray-900
   - ❌ WRONG: bg-background, text-foreground, bg-primary, bg-muted, text-secondary
   - Use ONLY classes from the official Tailwind CSS documentation
5. **FILE COUNT LIMITS**:
   - Simple style/text change = 1 file ONLY
   - New component = 2 files MAX (component + parent)
   - If >3 files, YOU'RE DOING TOO MUCH

COMPONENT RELATIONSHIPS (CHECK THESE FIRST):
- Navigation usually lives INSIDE Header.jsx, not separate Nav.jsx
- Logo is typically in Header, not standalone
- Footer often contains nav links already
- Menu/Hamburger is part of Header, not separate

PACKAGE USAGE RULES:
- DO NOT use react-router-dom unless user explicitly asks for routing
- For simple nav links in a single-page app, use scroll-to-section or href="#"
- Only add routing if building a multi-page application
- Common packages are auto-installed from your imports

WEBSITE CLONING REQUIREMENTS:
When recreating/cloning a website, you MUST include:
1. **Header with Navigation** - Usually Header.jsx containing nav
2. **Hero Section** - The main landing area (Hero.jsx)
3. **Main Content Sections** - Features, Services, About, etc.
4. **Footer** - Contact info, links, copyright (Footer.jsx)
5. **App.jsx** - Main app component that imports and uses all components



"""
    guardrails = f"""
🔒 HIGHEST-PRIORITY UI DESIGN GUARDRAILS (MUST FOLLOW EXACTLY; OVERRIDE STYLE CONFLICTS)
The following design principles MUST be respected in every output. If a user request contradicts these, apply these rules first and still satisfy the request within these constraints.

{ui_rules}

— End of Guardrails —
"""
    # Add edit mode instructions if this is an edit
    if is_edit:
        system_prompt += """CRITICAL: THIS IS AN EDIT TO AN EXISTING APPLICATION

YOU MUST FOLLOW THESE EDIT RULES:
0. NEVER create tailwind.config.js, vite.config.js, package.json, or any other config files - they already exist!
1. DO NOT regenerate the entire application
2. DO NOT create files that already exist (like App.jsx, index.css, tailwind.config.js)
3. ONLY edit the EXACT files needed for the requested change - NO MORE, NO LESS
4. If the user says "update the header", ONLY edit the Header component - DO NOT touch Footer, Hero, or any other components
5. If the user says "change the color", ONLY edit the relevant style or component file - DO NOT "improve" other parts
6. If you're unsure which file to edit, choose the SINGLE most specific one related to the request
7. IMPORTANT: When adding new components or libraries:
   - Create the new component file
   - UPDATE ONLY the parent component that will use it
   - Example: Adding a Newsletter component means:
     * Create Newsletter.jsx
     * Update ONLY the file that will use it (e.g., Footer.jsx OR App.jsx) - NOT both
8. When adding npm packages:
   - Import them ONLY in the files where they're actually used
   - The system will auto-install missing packages

CRITICAL FILE MODIFICATION RULES - VIOLATION = FAILURE:
- **NEVER TRUNCATE FILES** - Always return COMPLETE files with ALL content
- **NO ELLIPSIS (...)** - Include every single line of code, no skipping
- Files MUST be complete and runnable - include ALL imports, functions, JSX, and closing tags
- Count the files you're about to generate
- If the user asked to change ONE thing, you should generate ONE file (or at most two if adding a new component)
- DO NOT "fix" or "improve" files that weren't mentioned in the request
- DO NOT update multiple components when only one was requested
- DO NOT add features the user didn't ask for
- RESIST the urge to be "helpful" by updating related files

CRITICAL: DO NOT REDESIGN OR REIMAGINE COMPONENTS
- "update" means make a small change, NOT redesign the entire component
- "change X to Y" means ONLY change X to Y, nothing else
- "fix" means repair what's broken, NOT rewrite everything
- "remove X" means delete X from the existing file, NOT create a new file
- "delete X" means remove X from where it currently exists
- Preserve ALL existing functionality and design unless explicitly asked to change it

NEVER CREATE NEW FILES WHEN THE USER ASKS TO REMOVE/DELETE SOMETHING
If the user says "remove X", you must:
1. Find which existing file contains X
2. Edit that file to remove X
3. DO NOT create any new files

"""

        # Add targeted edit mode if we have edit context
        if edit_context:
            system_prompt += f"""
TARGETED EDIT MODE ACTIVE
- Edit Type: {edit_context.get('editIntent', {}).get('type', 'UPDATE')}
- Confidence: {edit_context.get('editIntent', {}).get('confidence', 0.8)}
- Files to Edit: {', '.join(edit_context.get('primaryFiles', []))}

🚨 CRITICAL RULE - VIOLATION WILL RESULT IN FAILURE 🚨
YOU MUST ***ONLY*** GENERATE THE FILES LISTED ABOVE!

ABSOLUTE REQUIREMENTS:
1. COUNT the files in "Files to Edit" - that's EXACTLY how many files you must generate
2. If "Files to Edit" shows ONE file, generate ONLY that ONE file
3. DO NOT generate App.jsx unless it's EXPLICITLY listed in "Files to Edit"
4. DO NOT generate ANY components that aren't listed in "Files to Edit"
5. DO NOT "helpfully" update related files
6. DO NOT fix unrelated issues you notice
7. DO NOT improve code quality in files not being edited
8. DO NOT add bonus features

EXAMPLE VIOLATIONS (THESE ARE FAILURES):
❌ User says "update the hero" → You update Hero, Header, Footer, and App.jsx
❌ User says "change header color" → You redesign the entire header
❌ User says "fix the button" → You update multiple components
❌ Files to Edit shows "Hero.jsx" → You also generate App.jsx "to integrate it"
❌ Files to Edit shows "Header.jsx" → You also update Footer.jsx "for consistency"

CORRECT BEHAVIOR (THIS IS SUCCESS):
✅ User says "update the hero" → You ONLY edit Hero.jsx with the requested change
✅ User says "change header color" → You ONLY change the color in Header.jsx
✅ User says "fix the button" → You ONLY fix the specific button issue
✅ Files to Edit shows "Hero.jsx" → You generate ONLY Hero.jsx
✅ Files to Edit shows "Header.jsx, Nav.jsx" → You generate EXACTLY 2 files: Header.jsx and Nav.jsx

THE AI INTENT ANALYZER HAS ALREADY DETERMINED THE FILES.
DO NOT SECOND-GUESS IT.
DO NOT ADD MORE FILES.
ONLY OUTPUT THE EXACT FILES LISTED IN "Files to Edit".

"""

        system_prompt += """VIOLATION OF THESE RULES WILL RESULT IN FAILURE!

"""
    system_prompt+=guardrails
    # Add the rest of the comprehensive prompt
    system_prompt += """CRITICAL INCREMENTAL UPDATE RULES:
- When the user asks for additions or modifications (like "add a videos page", "create a new component", "update the header"):
  - DO NOT regenerate the entire application
  - DO NOT recreate files that already exist unless explicitly asked
  - ONLY create/modify the specific files needed for the requested change
  - Preserve all existing functionality and files
  - If adding a new page/route, integrate it with the existing routing system
  - Reference existing components and styles rather than duplicating them
  - NEVER recreate config files (tailwind.config.js, vite.config.js, package.json, etc.)

IMPORTANT: When the user asks for edits or modifications:
- You have access to the current file contents in the context
- Make targeted changes to existing files rather than regenerating everything
- Preserve the existing structure and only modify what's requested
- If you need to see a specific file that's not in context, mention it

IMPORTANT: You have access to the full conversation context including:
- Previously scraped websites and their content
- Components already generated and applied
- The current project being worked on
- Recent conversation history
- Any Vite errors that need to be resolved

When the user references "the app", "the website", or "the site" without specifics, refer to:
1. The most recently scraped website in the context
2. The current project name in the context
3. The files currently in the sandbox

If you see scraped websites in the context, you're working on a clone/recreation of that site.

CRITICAL UI/UX RULES:
- NEVER use emojis in any code, text, console logs, or UI elements
- ALWAYS ensure responsive design using proper Tailwind classes (sm:, md:, lg:, xl:)
- ALWAYS use proper mobile-first responsive design patterns
- NEVER hardcode pixel widths - use relative units and responsive classes
- ALWAYS test that the layout works on mobile devices (320px and up)
- ALWAYS make sections full-width by default - avoid max-w-7xl or similar constraints
- For full-width layouts: use className="w-full" or no width constraint at all
- Only add max-width constraints when explicitly needed for readability (like blog posts)
- Prefer system fonts and clean typography
- Ensure all interactive elements have proper hover/focus states
- Use proper semantic HTML elements for accessibility

CRITICAL STYLING RULES - MUST FOLLOW:
- NEVER use inline styles with style={{}} in JSX
- NEVER use <style jsx> tags or any CSS-in-JS solutions
- NEVER create App.css, Component.css, or any component-specific CSS files
- NEVER import './App.css' or any CSS files except index.css
- ALWAYS use Tailwind CSS classes for ALL styling
- ONLY create src/index.css with the @tailwind directives
- The ONLY CSS file should be src/index.css with:
  @tailwind base;
  @tailwind components;
  @tailwind utilities;
- Use Tailwind's full utility set: spacing, colors, typography, flexbox, grid, animations, etc.
- ALWAYS add smooth transitions and animations where appropriate:
  - Use transition-all, transition-colors, transition-opacity for hover states
  - Use animate-fade-in, animate-pulse, animate-bounce for engaging UI elements
  - Add hover:scale-105 or hover:scale-110 for interactive elements
  - Use transform and transition utilities for smooth interactions
- For complex layouts, combine Tailwind utilities rather than writing custom CSS
- NEVER use non-standard Tailwind classes like "border-border", "bg-background", "text-foreground", etc.
- Use standard Tailwind classes only:
  - For borders: use "border-gray-200", "border-gray-300", etc. NOT "border-border"
  - For backgrounds: use "bg-white", "bg-gray-100", etc. NOT "bg-background"
  - For text: use "text-gray-900", "text-black", etc. NOT "text-foreground"
- Examples of good Tailwind usage:
  - Buttons: className="px-4 py-2 bg-blue-600 text-white rounded-lg shadow-md hover:bg-blue-700 hover:shadow-lg transform hover:scale-105 transition-all duration-200"
  - Cards: className="bg-white rounded-lg shadow-md p-6 border border-gray-200 hover:shadow-xl transition-shadow duration-300"
  - Full-width sections: className="w-full px-4 sm:px-6 lg:px-8"
  - Constrained content (only when needed): className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8"
  - Dark backgrounds: className="min-h-screen bg-gray-900 text-white"
  - Hero sections: className="animate-fade-in-up"
  - Feature cards: className="transform hover:scale-105 transition-transform duration-300"
  - CTAs: className="animate-pulse hover:animate-none"

CRITICAL STRING AND SYNTAX RULES:
- ALWAYS escape apostrophes in strings: use \\\' instead of ' or use double quotes
- ALWAYS escape quotes properly in JSX attributes
- NEVER use curly quotes or smart quotes ('' "" '' "") - only straight quotes (' ")
- ALWAYS convert smart/curly quotes to straight quotes:
  - ' and ' → '
  - " and " → "
  - Any other Unicode quotes → straight quotes
- When strings contain apostrophes, either:
  1. Use double quotes: "you're" instead of 'you're'
  2. Escape the apostrophe: 'you\\\\'re'
- When working with scraped content, ALWAYS sanitize quotes first
- Replace all smart quotes with straight quotes before using in code
- Be extra careful with user-generated content or scraped text
- Always validate that JSX syntax is correct before generating

CRITICAL CODE SNIPPET DISPLAY RULES:
- When displaying code examples in JSX, NEVER put raw curly braces {{ }} in text
- ALWAYS wrap code snippets in template literals with backticks
- For code examples in components, use one of these patterns:
  1. Template literals: <div>{\\`const example = {{ key: 'value' }}\\`}</div>
  2. Pre/code blocks: <pre><code>{\\`your code here\\`}</code></pre>
  3. Escape braces: <div>{'{'}key: value{'}'}</div>
- NEVER do this: <div>const example = {{ key: 'value' }}</div> (causes parse errors)
- For multi-line code snippets, always use:
  <pre className="bg-gray-900 text-gray-100 p-4 rounded">
    <code>{\\`
      // Your code here
      const example = {{
        key: 'value'
      }}
    \\`}</code>
  </pre>

CRITICAL: When asked to create a React app or components:
- ALWAYS CREATE ALL FILES IN FULL - never provide partial implementations
- ALWAYS CREATE EVERY COMPONENT that you import - no placeholders
- ALWAYS IMPLEMENT COMPLETE FUNCTIONALITY - don't leave TODOs unless explicitly asked
- If you're recreating a website, implement ALL sections and features completely
- NEVER create tailwind.config.js - it's already configured in the template
- ALWAYS include a Navigation/Header component (Nav.jsx or Header.jsx) - websites need navigation!

REQUIRED COMPONENTS for website clones:
1. Nav.jsx or Header.jsx - Navigation bar with links (NEVER SKIP THIS!)
2. Hero.jsx - Main landing section
3. Features/Services/Products sections - Based on the site content
4. Footer.jsx - Footer with links and info
5. App.jsx - Main component that imports and arranges all components
- NEVER create vite.config.js - it's already configured in the template
- NEVER create package.json - it's already configured in the template

WHEN WORKING WITH SCRAPED CONTENT:
- ALWAYS sanitize all text content before using in code
- Convert ALL smart quotes to straight quotes
- Example transformations:
  - "Firecrawl's API" → "Firecrawl's API" or "Firecrawl\\\\'s API"
  - 'It's amazing' → "It's amazing" or 'It\\\\'s amazing'
  - "Best tool ever" → "Best tool ever"
- When in doubt, use double quotes for strings containing apostrophes
- For testimonials or quotes from scraped content, ALWAYS clean the text:
  - Bad: content: 'Moved our internal agent's web scraping...'
  - Good: content: "Moved our internal agent's web scraping..."
  - Also good: content: 'Moved our internal agent\\\\'s web scraping...'

🚨 CRITICAL OUTPUT FORMAT - MUST USE THIS EXACT FORMAT:

<file path="src/index.css">
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {{
  font-family: Inter, system-ui, Avenir, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  font-weight: 400;
}}

body {{
  margin: 0;
  display: flex;
  place-items: center;
  min-width: 320px;
  min-height: 100vh;
}}
</file>

<file path="src/App.jsx">
import React from 'react'
import Header from './components/Header'
import Hero from './components/Hero'
import Footer from './components/Footer'

function App() {{
  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <Hero />
      <Footer />
    </div>
  )
}}

export default App
</file>

<file path="src/components/Header.jsx">
import React from 'react'

function Header() {{
  return (
    <header className="bg-white shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center py-6">
          <div className="flex-shrink-0">
            <h1 className="text-2xl font-bold text-gray-900">Logo</h1>
          </div>
          <nav className="hidden md:flex space-x-8">
            <a href="#home" className="text-gray-700 hover:text-blue-600">Home</a>
            <a href="#about" className="text-gray-700 hover:text-blue-600">About</a>
            <a href="#contact" className="text-gray-700 hover:text-blue-600">Contact</a>
          </nav>
        </div>
      </div>
    </header>
  )
}}

export default Header
</file>

🚨 CRITICAL: ALWAYS USE THE EXACT XML FORMAT ABOVE
- Every file MUST start with <file path="..."> and end with </file>
- File paths MUST be correct (src/App.jsx, src/components/ComponentName.jsx)
- NO OTHER FORMAT WILL WORK

CRITICAL COMPLETION RULES:
1. NEVER say "I'll continue with the remaining components"
2. NEVER say "Would you like me to proceed?"
3. NEVER use <continue> tags
4. Generate ALL components in ONE response
5. If App.jsx imports 10 components, generate ALL 10
6. Complete EVERYTHING before ending your response

When generating code, FOLLOW THIS PROCESS:
1. ALWAYS generate src/index.css FIRST - this establishes the styling foundation
2. List ALL components you plan to import in App.jsx
3. Count them - if there are 10 imports, you MUST create 10 component files
4. Generate src/index.css first (with proper CSS reset and base styles)
5. Generate src/App.jsx second
6. Then generate EVERY SINGLE component file you imported
7. Do NOT stop until all imports are satisfied

Use this XML format for React components only (DO NOT create tailwind.config.js - it already exists):

With 16,000 tokens available, you have plenty of space to generate a complete application. Use it!

🚨 CRITICAL CODE GENERATION RULES - VIOLATION = FAILURE 🚨:
1. NEVER truncate ANY code - ALWAYS write COMPLETE files
2. NEVER use "..." anywhere in your code - this causes syntax errors
3. NEVER cut off strings mid-sentence - COMPLETE every string
4. NEVER leave incomplete class names or attributes
5. ALWAYS close ALL tags, quotes, brackets, and parentheses
6. If you run out of space, prioritize completing the current file

UNDERSTANDING USER INTENT FOR INCREMENTAL VS FULL GENERATION:
- "add/create/make a [specific feature]" → Add ONLY that feature to existing app
- "add a videos page" → Create ONLY Videos.jsx and update routing
- "update the header" → Modify ONLY header component
- "fix the styling" → Update ONLY the affected components
- "change X to Y" → Find the file containing X and modify it
- "make the header black" → Find Header component and change its color
- "rebuild/recreate/start over" → Full regeneration
- Default to incremental updates when working on an existing app

SURGICAL EDIT RULES (CRITICAL FOR PERFORMANCE):
- **PREFER TARGETED CHANGES**: Don't regenerate entire components for small edits
- For color/style changes: Edit ONLY the specific className or style prop
- For text changes: Change ONLY the text content, keep everything else
- For adding elements: INSERT into existing JSX, don't rewrite the whole return
- **PRESERVE EXISTING CODE**: Keep all imports, functions, and unrelated code exactly as-is
- Maximum files to edit:
  - Style change = 1 file ONLY
  - Text change = 1 file ONLY
  - New feature = 2 files MAX (feature + parent)
- If you're editing >3 files for a simple request, STOP - you're doing too much

EXAMPLES OF CORRECT SURGICAL EDITS:
✅ "change header to black" → Find className="..." in Header.jsx, change ONLY color classes
✅ "update hero text" → Find the <h1> or <p> in Hero.jsx, change ONLY the text inside
✅ "add a button to hero" → Find the return statement, ADD button, keep everything else
❌ WRONG: Regenerating entire Header.jsx to change one color
❌ WRONG: Rewriting Hero.jsx to add one button

NAVIGATION/HEADER INTELLIGENCE:
- ALWAYS check App.jsx imports first
- Navigation is usually INSIDE Header.jsx, not separate
- If user says "nav", check Header.jsx FIRST
- Only create Nav.jsx if no navigation exists anywhere
- Logo, menu, hamburger = all typically in Header

CRITICAL: When files are provided in the context:
1. The user is asking you to MODIFY the existing app, not create a new one
2. Find the relevant file(s) from the provided context
3. Generate ONLY the files that need changes
4. Do NOT ask to see files - they are already provided in the context above
5. Make the requested change immediately

REMEMBER: It's better to generate fewer COMPLETE files than many INCOMPLETE files."""

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
                parts.append(f'- Change: ONLY the styling/theme as requested')
                parts.append(f'- Output: Complete files with preserved content + requested changes')

        # Include scraped website data for initial generation only
        elif not is_edit and context.get("conversationContext") and context["conversationContext"].get("scrapedWebsites"):
            parts.append("\n🌐 SCRAPED WEBSITE DATA:")
            for site in context["conversationContext"]["scrapedWebsites"]:
                parts.append(f"\nURL: {site.get('url', 'N/A')}")
                
                structured_data = site.get("structured", {})
                
                if structured_data.get("analysis"):
                    analysis = structured_data["analysis"]
                    parts.append(f"\n📊 ANALYSIS: {len(analysis.get('required_components', []))} components required")
                
                content_preview_text = structured_data.get("content", "")
                if content_preview_text:
                    parts.append(f"\n📄 CONTENT:\n{content_preview_text[:2000]}")

        if parts:
            full_prompt = f"CONTEXT:\n{chr(10).join(parts)}\n\n🎯 USER REQUEST:\n{prompt}"

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
    """FIXED: Enhanced AI response parser with robust file detection and UTF-8 sanitization"""
    
    # CRITICAL: Sanitize the entire content first to prevent UTF-8 issues
    content = sanitize_content_for_utf8(content)
    
    files: List[Dict[str, str]] = []

    print(f"[parse_files] Analyzing {len(content)} characters")

    # Strategy 1: Standard XML format (preferred)
    xml_pattern = r'<file\s+path="([^"]+)">(.*?)</file>'
    xml_matches = re.findall(xml_pattern, content, re.DOTALL)
    
    if xml_matches:
        print(f"[parse_files] Found {len(xml_matches)} XML files")
        for path, file_content in xml_matches:
            cleaned_content = sanitize_content_for_utf8(file_content.strip())
            if cleaned_content:
                # Add JSX validation
                cleaned_content = validate_jsx_syntax(cleaned_content, path)
                files.append({"path": path, "content": cleaned_content})
                print(f"[parse_files] Parsed: {path} ({len(cleaned_content)} chars)")
        return files

    # Strategy 2: Incomplete XML (streaming or cut-off)
    incomplete_pattern = r'<file\s+path="([^"]+)">(.*?)(?=<file|$)'
    incomplete_matches = re.findall(incomplete_pattern, content, re.DOTALL)

    if incomplete_matches:
        print(f"[parse_files] Found {len(incomplete_matches)} incomplete XML files")
        for path, file_content in incomplete_matches:
            cleaned_content = sanitize_content_for_utf8(file_content.replace("</file>", "").strip())
            if cleaned_content and len(cleaned_content) > 10:
                # Add JSX validation
                cleaned_content = validate_jsx_syntax(cleaned_content, path)
                files.append({"path": path, "content": cleaned_content})
                print(f"[parse_files] Parsed incomplete: {path} ({len(cleaned_content)} chars)")
        return files

    # Strategy 3: Code blocks with file paths
    code_block_patterns = [
        r'```(?:jsx|js|javascript|tsx|ts|css)\s+(?:path=["\'`])?([^\s\n"\'`]+\.(?:jsx?|tsx?|css))\s*\n(.*?)\n```',
        r'```(?:jsx|js|javascript|tsx|ts|css)\s*\n(?://\s*)?([^\s\n]+\.(?:jsx?|tsx?|css))\s*\n(.*?)\n```',
    ]
    
    for pattern in code_block_patterns:
        code_matches = re.findall(pattern, content, re.DOTALL)
        if code_matches:
            print(f"[parse_files] Found {len(code_matches)} code block files")
            for path, file_content in code_matches:
                # Ensure path starts with src/ if it's a component
                if not path.startswith("src/") and (path.endswith('.jsx') or path.endswith('.tsx') or path.endswith('.js') or path.endswith('.ts')):
                    if "components/" in path:
                        path = "src/" + path
                    elif not path.startswith("/") and path != "index.css":
                        path = "src/" + path
                elif path == "index.css":
                    path = "src/index.css"
                
                cleaned_content = sanitize_content_for_utf8(file_content.strip())
                if cleaned_content:
                    # Add JSX validation
                    cleaned_content = validate_jsx_syntax(cleaned_content, path)
                    files.append({"path": path, "content": cleaned_content})
                    print(f"[parse_files] Parsed code block: {path}")
            return files

    # Strategy 4: Markdown-style file headers
    markdown_pattern = r'\*\*(src/[^*\n]+)\*\*\s*```(?:jsx|js|css|json)?\s*\n(.*?)\n```'
    markdown_matches = re.findall(markdown_pattern, content, re.DOTALL)

    if markdown_matches:
        print(f"[parse_files] Found {len(markdown_matches)} markdown files")
        for path, file_content in markdown_matches:
            cleaned_content = sanitize_content_for_utf8(file_content.strip())
            # Add JSX validation
            cleaned_content = validate_jsx_syntax(cleaned_content, path)
            files.append({"path": path, "content": cleaned_content})
            print(f"[parse_files] Parsed markdown: {path}")
        return files

    # Strategy 5: React component detection and intelligent extraction
    if "import React" in content or "function App" in content or "export default" in content:
        print("[parse_files] Detected React code, attempting intelligent extraction")

        # Try to find complete React components
        component_patterns = [
            # Full component with imports and export
            r'(import React.*?(?:export default \w+|export \{ \w+ as default \}))',
            # Just the component function/class
            r'((?:function|const) \w+.*?export default \w+)',
        ]

        extracted_components = []
        for pattern in component_patterns:
            matches = re.findall(pattern, content, re.DOTALL)
            extracted_components.extend(matches)

        if extracted_components:
            # Create App.jsx from the largest component
            largest_component = max(extracted_components, key=len)
            cleaned_content = sanitize_content_for_utf8(largest_component.strip())
            # Add JSX validation
            cleaned_content = validate_jsx_syntax(cleaned_content, "src/App.jsx")
            files.append({
                "path": "src/App.jsx",
                "content": cleaned_content
            })
            print("[parse_files] Extracted React component as App.jsx")

        # Always add a basic index.css for React apps
        if not any(f["path"].endswith("index.css") for f in files):
            css_content = sanitize_content_for_utf8("@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\nbody {\n  margin: 0;\n  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;\n  -webkit-font-smoothing: antialiased;\n  -moz-osx-font-smoothing: grayscale;\n}")
            files.append({
                "path": "src/index.css",
                "content": css_content
            })
            print("[parse_files] Added default index.css")

    # Strategy 6: Last resort - try to extract any code that looks like a file
    if not files:
        print("[parse_files] No files found, trying last resort extraction...")
        
        # Look for any JSX/JS content
        jsx_content = re.search(r'(function \w+.*?export default \w+)', content, re.DOTALL)
        if jsx_content:
            cleaned_content = sanitize_content_for_utf8(jsx_content.group(1).strip())
# Add JSX validation
            cleaned_content = validate_jsx_syntax(cleaned_content, "src/App.jsx")
            files.append({
                "path": "src/App.jsx",
                "content": cleaned_content
            })
            print("[parse_files] Last resort: extracted JSX as App.jsx")

        # Look for CSS content
        css_content = re.search(r'(@tailwind base;.*?)', content, re.DOTALL)
        if css_content:
            cleaned_content = sanitize_content_for_utf8(css_content.group(1).strip())
            files.append({
                "path": "src/index.css",
                "content": cleaned_content
            })
            print("[parse_files] Last resort: extracted CSS as index.css")

    # Final sanitization pass for all files
    for file_data in files:
        if 'content' in file_data:
            file_data['content'] = sanitize_content_for_utf8(file_data['content'])
            file_data['content'] = validate_jsx_syntax(file_data['content'], file_data['path'])

    print(f"[parse_files] Final result: {len(files)} files extracted")
    for f in files:
        print(f"[parse_files]   - {f['path']} ({len(f['content'])} chars)")

    return files

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
            for chunk in chain.stream({
                "system_prompt": state["system_prompt"],
                "full_prompt": state["full_prompt"]
            }):
                chunk_count += 1
                buffer.append(chunk)
                generated_code += chunk

                # Real-time file detection (improved)
                if '<file path="' in chunk and not in_file:
                    in_file = True
                    current_file_content = [chunk]
                    # Extract file path
                    path_match = re.search(r'<file path="([^"]+)"', chunk)
                    if path_match:
                        current_file_path = path_match.group(1)
                        print(f"[code_generation] 📝 Started parsing: {current_file_path}")
                elif in_file:
                    current_file_content.append(chunk)
                    if "</file>" in chunk:
                        # Complete file found
                        full_file_content = "".join(current_file_content)
                        file_match = re.search(r'<file path="([^"]+)">(.*?)</file>', full_file_content, re.DOTALL)
                        if file_match:
                            path, content = file_match.groups()
                            cleaned_content = content.strip()
                            if cleaned_content:
                                files.append({"path": path, "content": cleaned_content})
                                print(f"[code_generation] ✅ Real-time parsed: {path} ({len(cleaned_content)} chars)")

                                if "components/" in path:
                                    component_count += 1

                        in_file = False
                        current_file_content = []
                        current_file_path = ""

                # Send progress
                send_progress(state["progress_callbacks"], {
                    "type": "stream",
                    "text": chunk,
                    "raw": True
                })

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