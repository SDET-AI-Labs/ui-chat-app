"""Test UI test case insertion with region selector enforcement."""
import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path
sys.path.append('.')
from src.chatstack.tools.ui_insert import run, InvalidRegionSelectorError

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

async def test_region_selector_validation():
    await setup()

    try:
        # Ensure the data directory exists
        os.makedirs('./data', exist_ok=True)

        # Valid test case with specific region selector
        valid_test = {
            'module': 'Navigation',
            'description': 'Verify header logo',
            'url': 'http://localhost:8012/',
            'action_script': '''
            await page.goto(url)
            await page.waitForLoadState("load")
            return await page.screenshot(selector=region_selector)
            ''',
            'region_selector': '.header-logo',
            'expected': 'logo matches baseline'
        }
        
        print('Testing valid region selector...')
        result = await run({'test_cases': [valid_test]})
        print('Success:', result)
        
        # Test case missing region selector
        missing_selector = dict(valid_test)
        missing_selector['region_selector'] = ''
        
        print('\nTesting missing region selector...')
        try:
            result = await run({'test_cases': [missing_selector]})
            print('FAIL: Missing selector not detected:', result)
            return False
        except InvalidRegionSelectorError as e:
            print('Expected error:', str(e))
        
        # Test case with full page selector
        full_page = dict(valid_test)
        full_page['region_selector'] = 'body'
        
        print('\nTesting full page selector...')
        try:
            result = await run({'test_cases': [full_page]})
            print('FAIL: Full page selector not rejected:', result)
            return False
        except InvalidRegionSelectorError as e:
            print('Expected error:', str(e))
            
        # Test case with too generic selector
        generic = dict(valid_test)
        generic['region_selector'] = '*'
        
        print('\nTesting generic selector...')
        try:
            result = await run({'test_cases': [generic]})
            print('FAIL: Generic selector not rejected:', result)
            return False
        except InvalidRegionSelectorError as e:
            print('Expected error:', str(e))
            
        return True
        
    finally:
        await teardown()

if __name__ == '__main__':
    asyncio.run(test_region_selector_validation())