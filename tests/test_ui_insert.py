"""Test UI test case insertion with duplicate detection."""
import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path
sys.path.append('.')
from src.chatstack.tools.ui_insert import run

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

async def test_duplicate_detection():
    await setup()

    try:
        # Ensure the data directory exists
        os.makedirs('./data', exist_ok=True)

        # First test case
        test_case1 = {
            'module': 'Navigation',
            'description': 'Verify homepage title',
            'url': 'http://localhost:8012/',
            'validate_script': '''
            await page.goto(url)
            await page.waitForLoadState("load")
            return await page.title()
            ''',
            'expected_result': 'Home'
        }
        
        print('Inserting first test case...')
        result = await run({'test_cases': [test_case1]})
        print('Success:', result)
        
        print('\nTrying to insert duplicate with different whitespace...')
        test_case2 = dict(test_case1)
        test_case2['validate_script'] = 'await page.goto(url); await page.waitForLoadState("load"); return await page.title();'
        try:
            result = await run({'test_cases': [test_case2]})
            print('FAIL: Duplicate not detected:', result)
            return False
        except Exception as e:
            print('Expected error:', str(e))
        
        print('\nTrying to insert duplicate with different URL casing...')
        test_case3 = dict(test_case1)
        test_case3['url'] = 'HTTP://LOCALHOST:8012/'
        try:
            result = await run({'test_cases': [test_case3]})
            print('FAIL: Duplicate not detected:', result)
            return False
        except Exception as e:
            print('Expected error:', str(e))
            
        return True
        
    finally:
        await teardown()

if __name__ == '__main__':
    asyncio.run(test_duplicate_detection())