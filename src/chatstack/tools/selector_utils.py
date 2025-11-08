"""Normalize CSS selectors to canonical form."""
import re
from typing import Optional

def _strip_redundant_tag(selector: str) -> str:
    """Remove redundant element tags from selector if they don't add specificity.
    Hybrid C ruleset: Only remove div, span, section, main tags if they prefix a specific selector.
    """
    redundant_tags = {'div', 'span', 'section', 'main'}
    
    # Match tag[anything] or tag.class or tag#id patterns
    tag_pattern = r'^([a-zA-Z]+)([.#\[].*)'
    match = re.match(tag_pattern, selector)
    
    if match and match.group(1).lower() in redundant_tags:
        # Keep everything after the tag if it has class/id/attr
        return match.group(2)
    
    return selector

def _normalize_attribute_selectors(selector: str) -> str:
    """Normalize attribute selector syntax."""
    # Convert [attr="value"] to [attr=value] when quotes aren't needed
    selector = re.sub(r'\[([^=]+)=["\']([^"\'\[\]]+)["\']\]', r'[\1=\2]', selector)
    
    # Ensure spaces around operators in attribute selectors
    selector = re.sub(r'\[([^=]+)\s*([~|^$*]?=)\s*([^\]]+)\]', r'[\1\2\3]', selector)
    
    return selector

def _is_specific_selector(selector: str) -> bool:
    """Check if a selector has meaningful specificity."""
    # Has class, ID, or attribute
    return bool(re.search(r'[.#\[]', selector))

def _normalize_combinators(selector: str) -> str:
    """Normalize and simplify combinator expressions."""
    # Split into parts by combinators
    parts = re.split(r'\s*([>+~])\s*', selector)
    normalized_parts = []
    last_was_specific = False
    last_combinator = None
    
    for i, part in enumerate(parts):
        if part in {'>','~','+'}:
            last_combinator = part
        else:
            # Process non-combinator part
            part = part.strip()
            if not part:
                continue
                
            result = _strip_redundant_tag(part)
            if not result:
                continue
                
            is_specific = _is_specific_selector(result)
            
            if is_specific:
                # If we have a previous specific part, include the combinator
                if last_was_specific and last_combinator:
                    normalized_parts.append(last_combinator)
                normalized_parts.append(result)
                last_was_specific = True
            # Non-specific selector only included if it's the only one
            elif not normalized_parts:
                normalized_parts.append(result)
                last_was_specific = False
                
            last_combinator = None
    
    # Join with single spaces
    return ' '.join(normalized_parts)

def normalize_region_selector(selector: str) -> str:
    """Normalize region selector to canonical form to prevent duplicate bypassing.
    
    Hybrid C ruleset:
    1. Convert to lowercase
    2. Trim spaces
    3. Remove only generic tag prefixes if present: div, span, section, main
       (e.g., div.header-logo → .header-logo)
    4. Everything else untouched
    
    Examples:
        'DIV.header-logo' -> '.header-logo'
        'span.menu' -> '.menu'
        'main.content' -> '.content'
        'section.sidebar' -> '.sidebar'
        'nav.links' -> 'nav.links'  # nav not in removal list
        'article.text > p' -> 'article.text > p'  # no changes
        'div.header > span.icon' -> '.header > span.icon'  # only prefix removed
    """
    if not selector or not isinstance(selector, str):
        return ""
    
    # Convert to lowercase and trim
    selector = selector.lower().strip()
    
    # Split by commas for multiple selectors
    parts = selector.split(',')
    normalized = []
    
    for part in parts:
        part = part.strip()
        # Split by combinators with flexible whitespace
        tokens = re.split(r'\s*([>+~])\s*', part)
        processed = []
        
        for i, token in enumerate(tokens):
            if token in {'>', '+', '~'}:
                processed.append(f" {token} ")
            elif token.strip():
                # Only try to strip tag from individual selectors
                processed.append(_strip_redundant_tag(token.strip()))
        
        normalized.append(''.join(processed).strip())
    
    return ', '.join(normalized).strip()