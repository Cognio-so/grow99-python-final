# Simplified scrape_url_enhanced.py - Remove all hardcoding, let LLM handle everything

from typing import Any, Dict, Optional
import os
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, START, END

import re
from urllib.parse import urlparse

# Replace the is_valid_url function in scrape_url_enhanced.py with this:

import re
from urllib.parse import urlparse
def sanitize_quotes(text: str) -> str:
    """Clean smart quotes and problematic characters"""
    if not isinstance(text, str):
        return text
    
    # Replace smart quotes
    text = re.sub(r"[\u2018\u2019\u201A\u201B]", "'", text)
    text = re.sub(r"[\u201C\u201D\u201E\u201F]", '"', text)
    text = re.sub(r"[\u2013\u2014]", "-", text)
    text = re.sub(r"\u2026", "...", text)
    text = re.sub(r"\u00A0", " ", text)
    
    return text

def is_valid_url(url_string: str) -> bool:
    """Robust URL validation that distinguishes URLs from natural language text"""
    if not url_string or not isinstance(url_string, str):
        return False
    
    url_string = url_string.strip()
    
    # If it contains spaces, it's likely natural language, not a URL
    if ' ' in url_string:
        # Exception: if it starts with http/https and has no spaces after the domain
        if url_string.startswith(('http://', 'https://')):
            # Extract the part after protocol
            after_protocol = url_string[8:] if url_string.startswith('https://') else url_string[7:]
            # If there's a space before the first slash, it's not a valid URL
            if '/' in after_protocol:
                domain_part = after_protocol.split('/')[0]
            else:
                domain_part = after_protocol
            
            if ' ' in domain_part:
                return False
        else:
            return False
    
    # Check for common natural language patterns that aren't URLs
    natural_language_patterns = [
        r'^(create|make|build|design|develop)',
        r'^(please|can you|could you|i want|i need)',
        r'^(help me|show me|tell me)',
        r'(website|page|site|app|application)\s+(for|with|that|about)',
        r'use\s+(images|icons|colors)',
        r'(professional|beautiful|modern|clean)',
    ]
    
    for pattern in natural_language_patterns:
        if re.search(pattern, url_string.lower()):
            return False
    
    try:
        # Add protocol if missing, but only for potential URLs
        if not url_string.startswith(('http://', 'https://')):
            # Basic check: must contain a dot and no spaces
            if '.' not in url_string or ' ' in url_string:
                return False
            url_string = 'https://' + url_string
        
        result = urlparse(url_string)
        
        # Must have scheme and netloc
        if not all([result.scheme, result.netloc]):
            return False
        
        # Netloc must contain a dot (for domain.tld format)
        if '.' not in result.netloc:
            return False
        
        # Netloc shouldn't contain spaces
        if ' ' in result.netloc:
            return False
        
        # Check if netloc looks like a real domain
        # Should not contain common natural language words
        domain_words = result.netloc.lower().split('.')
        natural_words = {'create', 'make', 'build', 'design', 'develop', 'website', 'page', 'app', 'for', 'with', 'that', 'about', 'the', 'and', 'or', 'but', 'if', 'then', 'use', 'using', 'how', 'what', 'when', 'where', 'why', 'who'}
        
        # If the first part of domain contains natural language words, probably not a URL
        if domain_words[0] in natural_words:
            return False
        
        # Additional check: domain should be reasonably short for the main part
        if len(domain_words[0]) > 20:  # Reasonable domain length
            return False
            
        return True
        
    except Exception:
        return False


# Test the function with some examples:
def test_url_detection():
    """Test cases to verify URL detection works correctly"""
    test_cases = [
        # Should be detected as URLs
        ("https://google.com", True),
        ("http://example.com", True), 
        ("google.com", True),
        ("www.google.com", True),
        ("subdomain.example.com", True),
        ("https://growth99.com", True),
        
        # Should NOT be detected as URLs (natural language)
        ("create a landing page for dental hospital", False),
        ("make a website for my business", False),
        ("build a professional website", False),
        ("design a modern app", False),
        ("use images and icons", False),
        ("please create a beautiful website", False),
        ("I want a dental clinic website", False),
        ("help me build a portfolio site", False),
        ("website for restaurant with online ordering", False),
        ("create a landing page for dental hospital. Use images and icon.Maintain the ui to look professional and beautiful", False),
    ]
    
    print("Testing URL detection:")
    for test_input, expected in test_cases:
        result = is_valid_url(test_input)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{test_input[:50]}...' -> {result} (expected: {expected})")

# Uncomment to test:
# test_url_detection()


async def _firecrawl_fetch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch content from URL using Firecrawl"""
    url: Optional[str] = payload.get("url")
    if not url:
        raise ValueError("URL is required")

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY environment variable is not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    body = {
        "url": url,
        "formats": ["markdown", "html"],
        "waitFor": 5000,
        "timeout": 45000,
        "blockAds": True,
        "onlyMainContent": False,
        "includeTags": ["nav", "header", "main", "section", "footer", "article", "aside", "div"],
        "excludeTags": ["script", "style", "noscript", "iframe"],
    }

    async with httpx.AsyncClient(timeout=50.0) as client:
        resp = await client.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers=headers,
            content=json.dumps(body),
        )

    if resp.status_code < 200 or resp.status_code >= 300:
        raise RuntimeError(f"Firecrawl API error: {resp.text}")

    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Firecrawl API error: invalid JSON response ({e})")


def _compile_graph():
    """Simple graph for URL fetching"""
    graph = StateGraph(dict)

    async def fetch_node(state: Dict[str, Any]) -> Dict[str, Any]:
        chain = RunnableLambda(_firecrawl_fetch)
        data = await chain.ainvoke(state)
        return {"data": data}

    graph.add_node("fetch", fetch_node)
    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", END)
    return graph.compile()


_GRAPH = _compile_graph()


async def POST(req: Any) -> Dict[str, Any]:
    """
    Simplified POST: Handle URLs (scrape) or text (pass through) - let LLM do all analysis
    """
    try:
        # Parse request
        if hasattr(req, "json"):
            body = await req.json()
        elif isinstance(req, dict):
            body = req
        else:
            body = {}

        input_value = body.get("url", "").strip()
        style_context = body.get("style_context", "")
        
        if not input_value:
            return {"success": False, "error": "URL or description is required", "status": 400}

        print(f"[scrape-url-enhanced] Processing: {input_value[:100]}...")

        # Check if input is URL or text
        if is_valid_url(input_value):
            print(f"[scrape-url-enhanced] URL detected - scraping: {input_value}")
            
            # Scrape the URL
            result = await _GRAPH.ainvoke({"url": input_value})
            data = result.get("data", {})

            if not data.get("success") or not data.get("data"):
                raise RuntimeError("Failed to scrape content")

            scraped = data["data"]
            raw_content = scraped.get("markdown", "")
            metadata = scraped.get("metadata", {})
            
            # Clean the content
            content = sanitize_quotes(raw_content)
            title = sanitize_quotes(metadata.get("title", ""))
            description = sanitize_quotes(metadata.get("description", ""))
            
            # Simple formatted prompt for LLM - let it handle all analysis
            formatted_content = f"""WEBSITE SCRAPING RESULT:

URL: {input_value}
Title: {title}
Description: {description}

{f"STYLE CONTEXT: {style_context}" if style_context else ""}

SCRAPED CONTENT:
{content}

INSTRUCTION: Create a modern React website recreation of this scraped content. Analyze the content and determine what components are needed, what sections to include, and how to structure everything. Use your judgment to create the best possible website."""

            result_metadata = {
                "source": "url_scraping",
                "original_url": input_value,
                "title": title,
                "description": description,
                "content_length": len(content),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            
        else:
            print(f"[scrape-url-enhanced] Text description detected")
            
            # Text description - just pass it through with context
            content = sanitize_quotes(input_value)
            
            formatted_content = f"""TEXT DESCRIPTION REQUEST:

User Request: {content}

{f"STYLE CONTEXT: {style_context}" if style_context else ""}

INSTRUCTION: Create a complete React website based on this description. Analyze what type of business/website this is, determine appropriate sections and components, and build a professional, modern website that fulfills the user's requirements."""

            result_metadata = {
                "source": "text_description", 
                "original_description": input_value,
                "style_context": style_context,
                "content_length": len(content),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        print(f"[scrape-url-enhanced] Content prepared: {len(formatted_content)} chars")

        return {
            "success": True,
            "content": formatted_content,
            "metadata": result_metadata,
            "message": "Content processed successfully - LLM will handle all analysis and generation"
        }

    except Exception as error:
        print(f"[scrape-url-enhanced] Error: {error}")
        return {"success": False, "error": str(error), "status": 500}