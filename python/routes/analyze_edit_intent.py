
import os
import json
import re
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
import asyncio
# Prefer modern provider packages
from langchain_groq import ChatGroq
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

# Env-driven defaults
ANTHROPIC_MODEL_DEFAULT = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
OPENAI_MODEL_DEFAULT = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
GROQ_MODEL_DEFAULT = os.environ.get("GROQ_MODEL", "moonshotai/kimi-k2-instruct")
GOOGLE_MODEL_DEFAULT = os.environ.get("GOOGLE_MODEL", "gemini-1.5-pro")

def _clean_base_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return url[:-3] if url.endswith("/v1") else url

# Pseudo/alias models → real provider models
OSS_ALIASES = {
    "openai/gpt-oss-20b": ("groq", GROQ_MODEL_DEFAULT),
    "gpt-oss-20b": ("groq", GROQ_MODEL_DEFAULT),
}

def _build_anthropic(model_name: Optional[str] = None) -> ChatAnthropic:
    base_url = _clean_base_url(os.environ.get("ANTHROPIC_BASE_URL"))
    kwargs: Dict[str, Any] = {}
    if base_url:
        kwargs["base_url"] = base_url
    return ChatAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        model=model_name or ANTHROPIC_MODEL_DEFAULT,
        **kwargs,
    )

def _build_openai(model_name: Optional[str] = None) -> ChatOpenAI:
    base_url = os.environ.get("OPENAI_BASE_URL")
    kwargs: Dict[str, Any] = {}
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model=model_name or OPENAI_MODEL_DEFAULT,
        **kwargs,
    )

def _build_groq(model_name: Optional[str] = None) -> ChatGroq:
    return ChatGroq(
        api_key=os.environ.get("GROQ_API_KEY"),
        model=model_name or GROQ_MODEL_DEFAULT,
    )

def _build_google(model_name: Optional[str] = None) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        api_key=os.environ.get("GOOGLE_API_KEY"),
        model=model_name or GOOGLE_MODEL_DEFAULT,
    )

def _select_model(model_str: str):
    """Resolve a user-supplied model string"""
    # Handle aliases first
    if model_str in OSS_ALIASES:
        provider, real_model = OSS_ALIASES[model_str]
        if provider == "groq":
            return _build_groq(real_model)

    # Provider-prefixed
    if "/" in model_str:
        provider, name = model_str.split("/", 1)
        provider = provider.lower()
        if provider == "anthropic":
            return _build_anthropic(name)
        if provider == "openai":
            return _build_openai(name)
        if provider == "google":
            return _build_google(name)
        if provider == "groq":
            return _build_groq(name)

    # Fallback heuristics
    ms = model_str.lower()
    if ms.startswith("claude"):
        return _build_anthropic(model_str)
    if ms.startswith("gpt"):
        return _build_openai(model_str)
    if "gemini" in ms:
        return _build_google(model_str)
    if "kimi k2 instruct" in ms or "kimi-k2-instruct" in ms:
        return _build_groq(model_str)

    # Final fallback → Groq
    return _build_groq(model_str)

# Domain models
class EditType(str, Enum):
    UPDATE_COMPONENT = 'UPDATE_COMPONENT'
    ADD_FEATURE = 'ADD_FEATURE'
    FIX_ISSUE = 'FIX_ISSUE'
    UPDATE_STYLE = 'UPDATE_STYLE'
    REFACTOR = 'REFACTOR'
    ADD_DEPENDENCY = 'ADD_DEPENDENCY'
    REMOVE_ELEMENT = 'REMOVE_ELEMENT'
    ENHANCE_EXISTING = 'ENHANCE_EXISTING'  # New type for UI enhancements

class FallbackSearch(BaseModel):
    terms: List[str]
    patterns: Optional[List[str]] = None

class EditContextSchema(BaseModel):
    editType: EditType = Field(description='The type of edit being requested')
    reasoning: str = Field(description='Explanation of the edit strategy')
    primaryFiles: List[str] = Field(description='Main files that need to be edited')
    contextFiles: List[str] = Field(description='Additional files to include for context')
    preserveExisting: bool = Field(default=True, description='Whether to preserve existing content')
    enhanceOnly: bool = Field(default=False, description='Whether this is a visual enhancement only')
    targetSections: List[str] = Field(default=[], description='Specific sections to modify (e.g., hero, header)')
    expectedChanges: List[str] = Field(description='Expected types of changes')

def analyze_existing_files(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze existing files to understand the current structure"""
    print('[analyze_existing_files] 🔍 Analyzing current file structure...')
    
    files = manifest.get('files', {})
    components = {}
    main_files = []
    
    for file_path, file_info in files.items():
        if not isinstance(file_info, dict):
            continue
            
        content = file_info.get('content', '')
        relative_path = file_path.replace('/home/user/app/', '')
        
        print(f'[analyze_existing_files] 📄 Analyzing: {relative_path}')
        
        # Identify component types
        if relative_path.endswith('.jsx') or relative_path.endswith('.tsx'):
            component_name = relative_path.split('/')[-1].replace('.jsx', '').replace('.tsx', '')
            
            # Analyze what this component contains
            component_info = {
                'path': file_path,
                'relativePath': relative_path,
                'name': component_name,
                'content': content,
                'contentPreview': content[:300],
                'hasHero': 'hero' in content.lower() or 'Hero' in content,
                'hasHeader': 'header' in content.lower() or 'Header' in content or 'nav' in content.lower(),
                'hasFooter': 'footer' in content.lower() or 'Footer' in content,
                'hasFeatures': 'feature' in content.lower() or 'Feature' in content,
                'hasTestimonials': 'testimonial' in content.lower() or 'Testimonial' in content,
                'hasPricing': 'pricing' in content.lower() or 'Pricing' in content,
                'hasAbout': 'about' in content.lower() or 'About' in content,
                'hasContact': 'contact' in content.lower() or 'Contact' in content,
                'isMainApp': relative_path.endswith('App.jsx') or relative_path.endswith('App.tsx'),
                'wordCount': len(content.split()),
                'hasRealContent': len(content) > 500 and 'lorem ipsum' not in content.lower()
            }
            
            components[component_name] = component_info
            
            if component_info['isMainApp']:
                main_files.append(file_path)
                print(f'[analyze_existing_files] 🎯 Found main app: {relative_path}')
    
    print(f'[analyze_existing_files] ✅ Found {len(components)} components: {list(components.keys())}')
    
    return {
        'components': components,
        'mainFiles': main_files,
        'totalFiles': len(files),
        'hasRealContent': any(comp['hasRealContent'] for comp in components.values())
    }

import asyncio

def _detect_error_in_prompt(prompt: str) -> Dict[str, Any]:
    """Detect if the prompt contains an error message and extract error details"""
    
    prompt_lower = prompt.lower()
    
    # Common error patterns
    error_patterns = {
        'react_error': [
            'plugin:vite:react-babel', 'unexpected token', 'jsx', 'react error',
            'compilation failed', 'syntax error', 'unclosed', 'missing'
        ],
        'import_error': [
            'cannot resolve', 'module not found', 'failed to resolve import',
            'import error', 'missing module'
        ],
        'vite_error': [
            'plugin:vite', 'vite error', 'build failed', 'compilation error'
        ],
        'general_error': [
            'error', 'failed', 'exception', 'crash', 'broken'
        ]
    }
    
    detected_errors = []
    error_type = 'general_error'
    
    # Check for specific error patterns
    for pattern_name, patterns in error_patterns.items():
        for pattern in patterns:
            if pattern in prompt_lower:
                detected_errors.append({
                    'type': pattern_name,
                    'pattern': pattern,
                    'message': prompt
                })
                error_type = pattern_name
                break
        if detected_errors:
            break
    
    if detected_errors:
        return {
            'is_error': True,
            'errors': detected_errors,
            'error_type': error_type,
            'confidence': 0.9 if error_type != 'general_error' else 0.7
        }
    
    return {
        'is_error': False,
        'errors': [],
        'error_type': None,
        'confidence': 0.0
    }

def _extract_error_context(prompt: str, file_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Extract error context and identify affected files"""
    
    components = file_analysis.get('components', {})
    
    # Enhanced error pattern matching
    error_patterns = {
        'app_jsx_error': r'App\.jsx.*?line (\d+)',
        'syntax_error': r'syntax error|unexpected token',
        'import_error': r'import.*?error|cannot resolve',
        'component_error': r'component.*?error'
    }
    
    # Extract line numbers and file names from error
    line_number = None
    affected_file = None
    
    for pattern_name, pattern in error_patterns.items():
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            if pattern_name == 'app_jsx_error':
                line_number = int(match.group(1))
                affected_file = 'App.jsx'
            break
    
    # Look for file names in the error message
    mentioned_files = []
    for comp_name, comp_info in components.items():
        if isinstance(comp_info, dict):
            file_name = comp_info.get('name', '')
            if file_name.lower() in prompt.lower():
                mentioned_files.append(comp_info['path'])
    
    # For syntax errors, prioritize the file mentioned in the error
    if affected_file:
        for comp_info in components.values():
            if isinstance(comp_info, dict) and affected_file in comp_info.get('relativePath', ''):
                mentioned_files.insert(0, comp_info['path'])
    
    error_context = {
        'affected_files': mentioned_files,
        'line_number': line_number,
        'error_details': prompt,
        'error_type': 'syntax_error' if 'syntax' in prompt.lower() or 'unexpected token' in prompt.lower() else 'general_error'
    }
    
    print(f"[_extract_error_context] 🚨 Error context: {error_context}")
    return error_context

def determine_edit_strategy(prompt: str, file_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """LLM-only approach for intelligent edit analysis"""
    print(f'[determine_edit_strategy] 🤖 LLM analysis for: "{prompt}"')
    
    # STEP 0: Check if this is an error message
    error_detection = _detect_error_in_prompt(prompt)
    if error_detection['is_error']:
        print(f'[determine_edit_strategy] 🚨 Error detected: {error_detection["error_type"]}')
        error_context = _extract_error_context(prompt, file_analysis)
        
        return {
            'editType': 'FIX_ISSUE',
            'targetFiles': error_context['affected_files'] or error_context['likely_components'],
            'targetSections': ['error_fix'],
            'preserveExisting': True,
            'enhanceOnly': False,
            'confidence': error_detection['confidence'],
            'reasoning': f"Error fix for: {error_detection['error_type']}",
            'errorContext': error_context,
            'isErrorFix': True
        }
    
    components = file_analysis.get('components', {})
    
    # Use LLM analysis directly - no keyword fallback
    llm_result = _llm_analysis(prompt, file_analysis, components)
    
    print(f'[determine_edit_strategy] ✅ LLM analysis complete (confidence: {llm_result["confidence"]})')
    return llm_result

def _llm_analysis(prompt: str, file_analysis: Dict[str, Any], components: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced LLM-based analysis with intelligent file targeting"""
    
    file_summary = "\n".join([
        f"- {comp_info['relativePath']}: {comp_info['name']} ({'Main App' if comp_info.get('isMainApp') else 'Component'})" 
        for comp_name, comp_info in components.items() 
        if isinstance(comp_info, dict)
    ])
    
    # Enhanced error detection patterns
    error_patterns = [
        'error', 'failed', 'syntax', 'unexpected token', 'cannot resolve', 
        'compilation failed', 'plugin:vite', 'react-babel', 'module not found',
        'import', 'export', 'jsx', 'unclosed', 'missing', 'invalid'
    ]
    
    is_error = any(pattern in prompt.lower() for pattern in error_patterns)
    
    if is_error:
        system_prompt = f"""You are an expert React developer analyzing an ERROR MESSAGE. Your job is to identify which files need to be fixed.

ERROR MESSAGE: "{prompt}"

Available files:
{file_summary}

CRITICAL ERROR ANALYSIS INSTRUCTIONS:
1. Read the error message carefully
2. Identify the specific file(s) that contain the error
3. Determine what type of error it is (syntax, import, JSX, etc.)
4. Select ONLY the files that need to be modified to fix the error
5. For syntax errors, include the file mentioned in the error
6. For import errors, include both the importing file and the missing component
7. For JSX errors, include the component with the malformed JSX

Return ONLY valid JSON with this exact format:
{{
    "editType": "FIX_ISSUE",
    "targetFiles": ["src/App.jsx", "src/components/Header.jsx"],
    "reasoning": "Clear explanation of what needs to be fixed and why",
    "confidence": 0.9,
    "preserveExisting": true,
    "enhanceOnly": false
}}

Return ONLY the JSON, no other text."""
    else:
        system_prompt = f"""You are an expert React developer analyzing edit requests. Your job is to intelligently determine which files need to be modified based on the user's request.

Available files:
{file_summary}

User request: "{prompt}"

CRITICAL RULES:
1. For styling/theme/color changes: Target components that handle styling
2. For text/content changes: Target components that likely contain the text
3. For layout/structure changes: Be conservative and only modify what's necessary
4. For new features/pages: Include App.jsx for routing AND create new component files
5. For "create new X page": You MUST include App.jsx for routing AND specify new component files
6. App.jsx should only be modified for: routing changes, adding new pages, or major structural changes

EXAMPLES:
- "change theme to dark" → targetFiles: ["Header.jsx", "Hero.jsx"] (components with styling)
- "create a new pricing page" → targetFiles: ["App.jsx", "src/components/Pricing.jsx"] (routing + new component)
- "add a contact form" → targetFiles: ["App.jsx", "src/components/Contact.jsx"] (routing + new component)
- "replace text madam with ashish" → targetFiles: ["Hero.jsx", "About.jsx"] (components with text)

Return ONLY valid JSON with this exact format:
{{
    "editType": "UPDATE_STYLE|UPDATE_COMPONENT|ADD_FEATURE|FIX_ISSUE",
    "targetFiles": ["src/components/Header.jsx", "src/components/Hero.jsx"],
    "reasoning": "Clear explanation of why these files were chosen",
    "confidence": 0.9,
    "preserveExisting": true,
    "enhanceOnly": false
}}

Return ONLY the JSON, no other text."""

    try:
        llm = _select_model("openai/gpt-4o-mini")
        response = llm.invoke([{"role": "system", "content": system_prompt}])
        plan_text = response.content if hasattr(response, 'content') else str(response)
        
        # Enhanced JSON extraction with multiple fallback methods
        json_text = plan_text.strip()
        
        # Method 1: Look for JSON in code blocks
        if '```json' in json_text:
            start = json_text.find('```json') + 7
            end = json_text.find('```', start)
            if end != -1:
                json_text = json_text[start:end].strip()
        elif '```' in json_text:
            # Method 2: Look for any code block
            start = json_text.find('```') + 3
            end = json_text.find('```', start)
            if end != -1:
                json_text = json_text[start:end].strip()
        
        # Method 3: Look for JSON object directly
        if not json_text.startswith('{'):
            start = json_text.find('{')
            if start != -1:
                end = json_text.rfind('}') + 1
                if end > start:
                    json_text = json_text[start:end]
        
        # Method 4: Clean up common issues
        json_text = json_text.replace('\n', ' ').replace('\r', ' ')
        json_text = re.sub(r'\s+', ' ', json_text).strip()
        
        try:
            llm_plan = json.loads(json_text)
        except json.JSONDecodeError as json_error:
            print(f"[_llm_analysis] JSON parse error: {json_error}")
            print(f"[_llm_analysis] Attempted to parse: {json_text[:200]}...")
            
            # Try to fix common JSON issues
            if 'targetFiles' not in json_text:
                json_text = json_text.replace('"targetfiles"', '"targetFiles"')
            if 'editType' not in json_text:
                json_text = json_text.replace('"edittype"', '"editType"')
            
            try:
                llm_plan = json.loads(json_text)
            except json.JSONDecodeError:
                print(f"[_llm_analysis] Failed to fix JSON, using fallback")
                raise json_error
        
        # Convert relative paths to full paths
        target_files = []
        for suggested_file in llm_plan.get("targetFiles", []):
            for comp_info in components.values():
                if isinstance(comp_info, dict) and suggested_file in comp_info.get('relativePath', ''):
                    target_files.append(comp_info['path'])
                    break
        
        return {
            'editType': llm_plan.get("editType", "FIX_ISSUE" if is_error else "UPDATE_STYLE"),
            'targetFiles': target_files,
            'targetSections': llm_plan.get("targetSections", []), 
            'preserveExisting': llm_plan.get("preserveExisting", True),
            'enhanceOnly': llm_plan.get("enhanceOnly", False),
            'confidence': llm_plan.get("confidence", 0.7),
            'reasoning': llm_plan.get("reasoning", f"LLM analysis for: {prompt}"),
            'isErrorFix': is_error
        }
        
    except Exception as e:
        print(f"[_llm_analysis] Error: {e}")
        # Smart fallback based on prompt content
        if is_error:
            # For errors, target the main app and components
            app_files = [comp['path'] for comp in components.values() 
                        if isinstance(comp, dict) and comp.get('isMainApp')]
            component_files = [comp['path'] for comp in components.values() 
                             if isinstance(comp, dict) and not comp.get('isMainApp')]
            return {
                'editType': 'FIX_ISSUE',
                'targetFiles': app_files + component_files[:2],
                'targetSections': [],
                'preserveExisting': True,
                'enhanceOnly': False,
                'confidence': 0.5,
                'reasoning': f"Error fix fallback for: {prompt}",
                'isErrorFix': True
            }
        else:
            # For regular edits, target components only
            component_files = [comp['path'] for comp in components.values() 
                             if isinstance(comp, dict) and not comp.get('isMainApp')]
            return {
                'editType': 'UPDATE_STYLE',
                'targetFiles': component_files[:3],
                'targetSections': [],
                'preserveExisting': True,
                'enhanceOnly': True,
                'confidence': 0.5,
                'reasoning': f"LLM fallback for: {prompt}",
                'isErrorFix': False
            }

def build_edit_context(prompt: str, manifest: Dict[str, Any], strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Build comprehensive edit context with error handling"""
    print('[build_edit_context] 🔧 Building edit context...')
    
    # Get all existing files for context
    all_files = list(manifest.get('files', {}).keys())
    target_files = strategy['targetFiles']
    
    # CRITICAL FIX: Include existing content for target files
    existing_content = {}
    for file_path in target_files:
        if file_path in manifest.get('files', {}):
            existing_content[file_path] = manifest['files'][file_path].get('content', '')
            print(f'[build_edit_context] 📄 Loaded existing content for {file_path} ({len(existing_content[file_path])} chars)')
    
    # Include related files as context (not for editing, just for reference)
    context_files = []
    for file_path in all_files:
        if file_path not in target_files and file_path.endswith(('.jsx', '.tsx', '.js', '.ts')):
            context_files.append(file_path)
    
    # Limit context files to prevent overflow
    context_files = context_files[:3]
    target_sections = strategy.get('targetSections', [])
    
    # Build system prompt based on edit type
    if strategy.get('isErrorFix'):
        system_prompt = _build_error_fix_prompt(prompt, strategy, target_files, existing_content)
    elif strategy['enhanceOnly']:
        system_prompt = _build_enhancement_prompt(prompt, strategy, target_files, target_sections)
    else:
        system_prompt = _build_general_edit_prompt(prompt, strategy, target_files, target_sections)
    
    edit_context = {
        'editType': strategy['editType'],
        'reasoning': strategy['reasoning'],
        'primaryFiles': target_files,
        'contextFiles': context_files,
        'existingContent': existing_content,
        'preserveExisting': strategy['preserveExisting'],
        'enhanceOnly': strategy['enhanceOnly'],
        'targetSections': strategy['targetSections'],
        'systemPrompt': system_prompt,
        'isErrorFix': strategy.get('isErrorFix', False),
        'errorContext': strategy.get('errorContext', {}),
        'expectedChanges': [
            'Error fixes and corrections' if strategy.get('isErrorFix') else 'Visual styling improvements' if strategy['enhanceOnly'] else 'Component modifications',
            f"Changes to: {', '.join(strategy['targetSections']) if strategy['targetSections'] else 'general styling'}"
        ]
    }
    
    print(f'[build_edit_context] ✅ Context built for {len(target_files)} primary files, {len(context_files)} context files')
    print(f'[build_edit_context] 📄 Existing content loaded for {len(existing_content)} files')
    
    return edit_context

def _build_error_fix_prompt(prompt: str, strategy: Dict[str, Any], target_files: List[str], existing_content: Dict[str, str]) -> str:
    """Build specialized prompt for error fixing"""
    
    error_context = strategy.get('errorContext', {})
    line_number = error_context.get('line_number')
    error_type = error_context.get('error_type', 'general_error')
    
    # Extract the specific error details
    error_lines = prompt.split('\n')
    error_message = error_lines[0] if error_lines else prompt
    
    system_prompt = f""" CRITICAL ERROR FIX MODE - FIX THE SPECIFIC SYNTAX ERROR

ERROR MESSAGE: "{error_message}"
ERROR TYPE: {error_type}
LINE NUMBER: {line_number if line_number else 'Unknown'}
AFFECTED FILES: {', '.join([f.split('/')[-1] for f in target_files])}

 ERROR FIX INSTRUCTIONS:
1. Focus ONLY on fixing the syntax error mentioned in the error message
2. Look at the specific line number and character position
3. Fix ONLY the syntax issue - do not change other code
4. Preserve all existing functionality and content
5. Ensure the code compiles without errors

🔧 COMMON SYNTAX FIXES:
- Fix unclosed quotes, brackets, or parentheses
- Fix malformed JSX attributes
- Fix invalid CSS class names or URLs
- Fix import/export syntax
- Fix component naming issues

❌ DO NOT:
- Change functionality unrelated to the error
- Add new features
- Modify styling unless it's causing the error
- Remove existing content

CRITICAL: Output ONLY the fixed files. The syntax error must be resolved and the code must compile successfully.

EXISTING CONTENT TO FIX:
"""
    
    # Add the existing content that needs to be fixed
    for file_path in target_files:
        file_name = file_path.split('/')[-1]
        content = existing_content.get(file_path, '')
        if content:
            system_prompt += f"\n--- {file_name} ---\n{content}\n"
    
    return system_prompt

def _build_enhancement_prompt(prompt: str, strategy: Dict[str, Any], target_files: List[str], target_sections: List[str]) -> str:
    """Build specialized prompt for enhancement requests"""
    
    system_prompt = f"""🚨 CRITICAL ENHANCEMENT MODE - PRESERVE ALL EXISTING CONTENT

USER REQUEST: "{prompt}"
🎯 EDIT CONTEXT:
- Edit Type: {strategy.get('editType', 'UPDATE_COMPONENT')}
- Target Sections: {target_sections}
- Preserve Existing: {strategy.get('preserveExisting', True)}

🎯 ENHANCEMENT INSTRUCTIONS:
1. This is a VISUAL ENHANCEMENT request - DO NOT change text content
2. PRESERVE all existing text, links, and functionality
3. ONLY improve styling, colors, layout, and visual design
4. DO NOT add new sections or remove existing content
5. DO NOT change the website's purpose or message

 FILES TO ENHANCE:
{chr(10).join(f"- {f.split('/')[-1]}" for f in target_files)}

✅ ALLOWED CHANGES:
- Improve Tailwind CSS classes for better visual design
- Enhance colors, typography, spacing
- Add smooth transitions and hover effects
- Improve responsive design
- Better visual hierarchy

❌ FORBIDDEN CHANGES:
- Changing any text content
- Adding new sections not requested
- Removing existing functionality
- Changing component structure
- Adding placeholder/dummy content

CRITICAL: Output ONLY the files listed above with enhanced styling. Keep all existing content exactly as is."""

    return system_prompt

def _build_general_edit_prompt(prompt: str, strategy: Dict[str, Any], target_files: List[str], target_sections: List[str]) -> str:
    """Build specialized prompt for general edit requests"""
    
    system_prompt = f""" TARGETED EDIT MODE - MODIFY SPECIFIC COMPONENTS

USER REQUEST: "{prompt}"

🎯 EDIT CONTEXT:
- Edit Type: {strategy['editType'].value if hasattr(strategy['editType'], 'value') else strategy['editType']}
- Target Sections: {strategy['targetSections']}
- Preserve Existing: {strategy['preserveExisting']}

🔧 FILES TO EDIT:
{chr(10).join(f"- {f.split('/')[-1]}" for f in target_files)}

📋 EDIT REQUIREMENTS:
1. Make ONLY the changes requested by the user
2. {"PRESERVE all existing content and functionality" if strategy['preserveExisting'] else "Make necessary changes"}
3. DO NOT redesign the entire application
4. Focus on the specific request: "{prompt}"

CRITICAL: Output ONLY the files listed above with the requested changes."""
    
    return system_prompt

def analyze_edit_intent(prompt: str, manifest: Dict[str, Any], model: str = 'openai/gpt-4o-mini') -> Dict[str, Any]:
    try:
        print('[analyze-edit-intent] 🚀 Enhanced analysis starting...')
        print(f'[analyze-edit-intent] 📝 Prompt: "{prompt}"')
        print(f'[analyze-edit-intent] 🤖 Model: {model}')
        print(f'[analyze-edit-intent] 📊 Manifest files count: {len(manifest.get("files", {})) if manifest and manifest.get("files") else 0}')

        if not prompt or not manifest:
            return {'success': False, 'error': 'prompt and manifest are required'}

        # Step 1: Analyze existing files
        file_analysis = analyze_existing_files(manifest)
        print(f'[analyze-edit-intent] 🔍 File analysis complete - found {file_analysis["totalFiles"]} total files')
        
        if file_analysis['totalFiles'] == 0:
            print('[analyze-edit-intent] ❌ No files found in manifest')
            return {'success': False, 'error': 'No files found in manifest'}

        # Step 2: Determine edit strategy (now includes error detection)
        strategy = determine_edit_strategy(prompt, file_analysis)
        
        if not strategy['targetFiles']:
            print('[analyze-edit-intent] ⚠️ No target files identified')
            return {
                'success': False, 
                'error': 'Could not identify files to edit',
                'fileAnalysis': file_analysis,
                'strategy': strategy
            }

        # Step 3: Build edit context
        edit_context = build_edit_context(prompt, manifest, strategy)
        
        print('[analyze-edit-intent] ✅ Enhanced analysis complete')
        print(f'[analyze-edit-intent] 🎯 Will edit {len(edit_context["primaryFiles"])} files:')
        for file_path in edit_context['primaryFiles']:
            print(f'[analyze-edit-intent]   - {file_path.split("/")[-1]}')
        
        if strategy.get('isErrorFix'):
            print(f'[analyze-edit-intent] 🚨 Error fix mode: {strategy.get("reasoning", "")}')
        
        return {
            'success': True, 
            'editContext': edit_context,
            'fileAnalysis': file_analysis,
            'strategy': strategy
        }

    except Exception as error:
        print(f'[analyze-edit-intent] ❌ Error: {error}')
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(error)}

# POST function for API compatibility
def POST(body: Dict[str, Any]) -> Dict[str, Any]:
    """API endpoint wrapper"""
    prompt = body.get('prompt', '')
    manifest = body.get('manifest', {})
    model = body.get('model', 'openai/gpt-4o-mini')
    
    return analyze_edit_intent(prompt, manifest, model)