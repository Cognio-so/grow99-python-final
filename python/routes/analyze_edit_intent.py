# Fixed analyze_edit_intent.py - Enhanced file analysis and context building

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

def determine_edit_strategy(prompt: str, file_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Hybrid approach: keyword-first, LLM fallback"""
    print(f'[determine_edit_strategy] 🤔 Hybrid analysis for: "{prompt}"')
    
    prompt_lower = prompt.lower()
    components = file_analysis.get('components', {})
    
    # STEP 1: Try keyword-based analysis (fast, reliable)
    keyword_result = _keyword_analysis(prompt_lower, components)
    
    # STEP 2: Check if keyword analysis was confident
    if keyword_result['confidence'] >= 0.8 and keyword_result['targetFiles']:
        print(f'[determine_edit_strategy] ✅ Keyword analysis successful (confidence: {keyword_result["confidence"]})')
        return keyword_result
    
    # STEP 3: Fall back to LLM analysis for ambiguous cases
    print(f'[determine_edit_strategy] 🤖 Keyword uncertain (confidence: {keyword_result["confidence"]}), using LLM fallback')
    llm_result = _llm_analysis(prompt, file_analysis, components)
    
    # Combine results with LLM taking priority
    return {
        **keyword_result,
        **llm_result,
        'analysisMethod': 'llm_fallback',
        'keywordConfidence': keyword_result['confidence'],
        'reasoning': f"Keyword analysis uncertain, LLM analysis: {llm_result.get('reasoning', '')}"
    }

def _keyword_analysis(prompt_lower: str, components: Dict[str, Any]) -> Dict[str, Any]:
    """Fast keyword-based analysis"""
    
    # Enhanced keyword patterns
    patterns = {
        'style_theme': ['style', 'theme', 'color', 'gradient', 'design', 'appearance', 'professional', 'modern', 'dark', 'light'],
        'header': ['header', 'nav', 'navigation', 'menu', 'logo'],
        'hero': ['hero', 'landing', 'banner', 'main section'],
        'footer': ['footer', 'bottom'],
        'specific_component': ['button', 'form', 'card', 'modal'],
        'layout': ['layout', 'spacing', 'margin', 'padding', 'responsive'],
        'add_feature': ['add', 'create', 'new', 'make'],
        'remove': ['remove', 'delete', 'hide']
    }
    
    # Score each pattern
    pattern_scores = {}
    for pattern_name, keywords in patterns.items():
        score = sum(1 for keyword in keywords if keyword in prompt_lower)
        if score > 0:
            pattern_scores[pattern_name] = score
    
    # Determine target files based on strongest pattern
    target_files = []
    confidence = 0.0
    edit_type = "UPDATE_STYLE"
    
    if not pattern_scores:
        return {'targetFiles': [], 'confidence': 0.0, 'editType': edit_type}
    
    strongest_pattern = max(pattern_scores, key=pattern_scores.get)
    max_score = pattern_scores[strongest_pattern]
    
    # Map patterns to files
    if strongest_pattern == 'header':
        target_files = _find_components_by_type(components, ['header', 'nav'])
        confidence = min(0.9, 0.6 + (max_score * 0.1))
        edit_type = "UPDATE_COMPONENT"
        
    elif strongest_pattern == 'hero':
        target_files = _find_components_by_type(components, ['hero'])
        confidence = min(0.9, 0.6 + (max_score * 0.1))
        edit_type = "UPDATE_COMPONENT"
        
    elif strongest_pattern == 'style_theme':
        # For styling, target visual components
        target_files = _find_components_by_type(components, ['header', 'hero', 'app'])
        confidence = min(0.85, 0.5 + (max_score * 0.1))
        edit_type = "UPDATE_STYLE"
        
    elif strongest_pattern == 'add_feature':
        # For adding features, confidence is lower - often needs LLM
        target_files = _find_components_by_type(components, ['app'])
        confidence = 0.4  # Low confidence to trigger LLM
        edit_type = "ADD_FEATURE"
        
    else:
        # Generic fallback
        target_files = _find_components_by_type(components, ['app'])
        confidence = 0.3  # Low confidence
    
    return {
        'editType': edit_type,
        'targetFiles': target_files,
        'targetSections': [strongest_pattern],
        'preserveExisting': strongest_pattern in ['style_theme', 'layout'],
        'enhanceOnly': strongest_pattern == 'style_theme',
        'confidence': confidence,
        'reasoning': f"Keyword pattern: {strongest_pattern} (score: {max_score})"
    }

def _find_components_by_type(components: Dict[str, Any], types: List[str]) -> List[str]:
    """Find component files matching the given types"""
    target_files = []
    
    for comp_name, comp_info in components.items():
        if not isinstance(comp_info, dict):
            continue
            
        comp_name_lower = comp_name.lower()
        
        for target_type in types:
            if target_type in comp_name_lower:
                target_files.append(comp_info['path'])
                break
        
        # Special checks
        if 'app' in types and comp_info.get('isMainApp'):
            target_files.append(comp_info['path'])
    
    return target_files

def _llm_analysis(prompt: str, file_analysis: Dict[str, Any], components: Dict[str, Any]) -> Dict[str, Any]:
    """LLM-based analysis for complex cases"""
    
    file_summary = "\n".join([
        f"- {comp_info['relativePath']}: {comp_info['name']}" 
        for comp_name, comp_info in components.items() 
        if isinstance(comp_info, dict)
    ])
    
    system_prompt = f"""Analyze this edit request for a React app. Be conservative - only target files that DEFINITELY need changes.

Files available:
{file_summary}

User request: "{prompt}"

Return JSON with:
{{
    "editType": "UPDATE_STYLE|UPDATE_COMPONENT|ADD_FEATURE",
    "targetFiles": ["src/App.jsx"],
    "reasoning": "brief explanation",
    "confidence": 0.8
}}

CRITICAL: For styling changes, do NOT include App.jsx unless absolutely necessary."""

    try:
        llm = _select_model("openai/gpt-4o-mini")
        response = llm.invoke([{"role": "system", "content": system_prompt}])
        plan_text = response.content if hasattr(response, 'content') else str(response)
        
        # Extract JSON
        json_text = plan_text.strip()
        if '```json' in json_text:
            start = json_text.find('```json') + 7
            end = json_text.find('```', start)
            if end != -1:
                json_text = json_text[start:end].strip()
        
        llm_plan = json.loads(json_text)
        
        # Convert relative paths to full paths
        target_files = []
        for suggested_file in llm_plan.get("targetFiles", []):
            for comp_info in components.values():
                if isinstance(comp_info, dict) and suggested_file in comp_info.get('relativePath', ''):
                    target_files.append(comp_info['path'])
                    break
        
        return {
            'editType': llm_plan.get("editType", "UPDATE_STYLE"),
            'targetFiles': target_files,
            'preserveExisting': True,
            'enhanceOnly': llm_plan.get("editType") == "UPDATE_STYLE",
            'confidence': llm_plan.get("confidence", 0.7),
            'reasoning': llm_plan.get("reasoning", f"LLM analysis for: {prompt}")
        }
        
    except Exception as e:
        print(f"[_llm_analysis] Error: {e}")
        # Safe fallback
        app_files = [comp['path'] for comp in components.values() 
                    if isinstance(comp, dict) and comp.get('isMainApp')]
        return {
            'editType': "UPDATE_STYLE",
            'targetFiles': app_files[:1],
            'preserveExisting': True,
            'enhanceOnly': True,
            'confidence': 0.5,
            'reasoning': f"LLM fallback for: {prompt}"
        }
def build_edit_context(prompt: str, manifest: Dict[str, Any], strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Build comprehensive edit context"""
    print('[build_edit_context] 🔧 Building edit context...')
    
    # Get all existing files for context
    all_files = list(manifest.get('files', {}).keys())
    target_files = strategy['targetFiles']
    
    # Include related files as context (not for editing, just for reference)
    context_files = []
    for file_path in all_files:
        if file_path not in target_files and file_path.endswith(('.jsx', '.tsx', '.js', '.ts')):
            context_files.append(file_path)
    
    # Limit context files to prevent overflow
    context_files = context_files[:3]
    
    # Build system prompt
    if strategy['enhanceOnly']:
        system_prompt = f"""🚨 CRITICAL ENHANCEMENT MODE - PRESERVE ALL EXISTING CONTENT

USER REQUEST: "{prompt}"

🎯 ENHANCEMENT INSTRUCTIONS:
1. This is a VISUAL ENHANCEMENT request - DO NOT change text content
2. PRESERVE all existing text, links, and functionality
3. ONLY improve styling, colors, layout, and visual design
4. DO NOT add new sections or remove existing content
5. DO NOT change the website's purpose or message

🔧 FILES TO ENHANCE:
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

    else:
        system_prompt = f"""🚨 TARGETED EDIT MODE - MODIFY SPECIFIC COMPONENTS

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
    
    edit_context = {
        'editType': strategy['editType'],
        'reasoning': strategy['reasoning'],
        'primaryFiles': target_files,
        'contextFiles': context_files,
        'preserveExisting': strategy['preserveExisting'],
        'enhanceOnly': strategy['enhanceOnly'],
        'targetSections': strategy['targetSections'],
        'systemPrompt': system_prompt,
        'expectedChanges': [
            'Visual styling improvements' if strategy['enhanceOnly'] else 'Component modifications',
            f"Changes to: {', '.join(strategy['targetSections']) if strategy['targetSections'] else 'general styling'}"
        ]
    }
    
    print(f'[build_edit_context] ✅ Context built for {len(target_files)} primary files, {len(context_files)} context files')
    
    return edit_context

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

        # Step 2: Determine edit strategy
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