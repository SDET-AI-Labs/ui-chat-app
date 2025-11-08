"""Test UI test case region selector normalization."""
import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path
sys.path.append('.')
from src.chatstack.tools.ui_insert import run, InvalidRegionSelectorError
from src.chatstack.tools.selector_utils import normalize_region_selector

# Use a test-specific file to avoid interfering with real data
TEST_FILE = "./data/ui_tests_test.xlsx"

async def setup():
    """Clean up any existing test file."""
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

async def teardown():
    """Clean up test file."""
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

async def test_selector_normalization():
    await setup()

    try:
        # Base test case
        base_test = {
            'module': 'Navigation',
            'description': 'Verify header logo',
            'url': 'http://localhost:8012/',
            'action_script': '''
            await page.goto(url)
            await page.waitForLoadState("load")
            return await page.screenshot(selector=region_selector)
            ''',
            'expected': 'logo matches baseline'
        }

        print('\nTesting selector normalization...')
        
        # Test 1: Basic selector normalization
        test1 = dict(base_test)
        test1['region_selector'] = 'DIV.header-logo'
        print(f"\nTest 1 - Original: {test1['region_selector']}")
        result = await run({'test_cases': [test1]})
        print('Success:', result)
        
        # Test 2: Should detect as duplicate (normalized form)
        test2 = dict(base_test)
        test2['region_selector'] = 'div[class="header-logo"]'
        print(f"\nTest 2 - Trying duplicate with different form: {test2['region_selector']}")
        try:
            result = await run({'test_cases': [test2]})
            print('FAIL: Duplicate not detected')
            return False
        except Exception as e:
            print('Expected error:', str(e))
            
        # Test 3: Whitespace and combinator variations
        test3 = dict(base_test)
        test3['region_selector'] = 'div   >  .header-logo'
        print(f"\nTest 3 - Trying with different spacing: {test3['region_selector']}")
        try:
            result = await run({'test_cases': [test3]})
            print('FAIL: Normalized duplicate not detected')
            return False
        except Exception as e:
            print('Expected error:', str(e))

        # Test 4: Attribute selector variations
        test4 = dict(base_test)
        test4['region_selector'] = 'div[data-test="logo"]'
        print(f"\nTest 4 - New unique selector: {test4['region_selector']}")
        result = await run({'test_cases': [test4]})
        print('Success:', result)
        
        # Test 5: Should detect as duplicate of test4
        test5 = dict(base_test)
        test5['region_selector'] = '[data-test=logo]'
        print(f"\nTest 5 - Trying duplicate with simplified attributes: {test5['region_selector']}")
        try:
            result = await run({'test_cases': [test5]})
            print('FAIL: Attribute selector duplicate not detected')
            return False
        except Exception as e:
            print('Expected error:', str(e))
            
        return True
        
    finally:
        await teardown()

def test_normalize_function():
    """Test selector normalization directly."""
    test_cases = [
        # Basic normalization
        ('DIV.header-logo', '.header-logo'),
        ('span.menu', '.menu'),
        ('main.content', '.content'),
        ('section.sidebar', '.sidebar'),
        
        # Tags that should NOT be removed
        ('nav.links', 'nav.links'),
        ('article.text', 'article.text'),
        ('p.description', 'p.description'),
        
        # Complex selectors
        ('div.header > span.icon', '.header > .icon'),
        ('main.content > article.text', '.content > article.text'),
        ('section.sidebar > p.info', '.sidebar > p.info'),
        
        # Spacing variations
        ('div.nav    >   span.item', '.nav > .item'),
        ('main.content>p.text', '.content > p.text'),
        
        # Multiple selectors
        ('div.header, span.footer', '.header, .footer'),
        ('main.content, section.aside', '.content, .aside'),
        
        # Leave non-removable tags intact
        ('header.top > footer.bottom', 'header.top > footer.bottom'),
    ]
    
    print('\nTesting normalize_region_selector function:')
    for original, expected in test_cases:
        result = normalize_region_selector(original)
        print(f"\nOriginal : {original}")
        print(f"Expected: {expected}")
        print(f"Got     : {result}")
        assert result == expected, f"Expected {expected}, got {result}"

if __name__ == '__main__':
    # Test normalize function directly
    test_normalize_function()
    
    # Test duplicate detection with normalized selectors
    asyncio.run(test_selector_normalization())