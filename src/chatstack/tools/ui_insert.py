"""UI test case insertion with uniqueness enforcement."""
from typing import Dict, Any, List
from pathlib import Path
import openpyxl
import json
import hashlib
import re
from datetime import datetime

from . import run_excel_suite

# Configuration constants
UI_TEST_FILE = "./data/ui_tests_test.xlsx"  # Use test file during development
UI_TEST_SHEET = "ui_tests"

class DuplicateTestError(Exception):
    """Raised when attempting to insert a duplicate test case."""
    pass

def _normalize_script(script: str) -> str:
    """Normalize script by removing whitespace and comments."""
    if not script:
        return ""
    
    # Normalize newlines and remove comments
    lines = []
    for line in script.splitlines():
        line = line.split('#')[0].strip()  # Remove comments
        if line:  # Skip empty lines
            lines.append(line)
            
    # Join all into one line
    script = ' '.join(lines)
    
    # Replace all semicolons with newlines, then normalize again
    script = script.replace(';', '\n')
    lines = [line.strip() for line in script.splitlines() if line.strip()]
    
    # Join back to single line and normalize whitespace
    normalized = ' '.join(lines)
    normalized = re.sub(r'\s+', ' ', normalized)  # Replace multiple spaces with single space
    return normalized.strip()

def _generate_test_key(test_case: Dict[str, Any]) -> str:
    """Generate uniqueness key for test case.
    
    Key = SHA256(normalized_url::normalized_script)
    where:
    - url is lowercased + trimmed
    - script has whitespace and comments removed
    """
    # Normalize URL: lowercase and trim
    url = str(test_case.get('url', '')).strip().lower()
    
    # Normalize script
    script = _normalize_script(str(test_case.get('validate_script', '')))
    
    # Create key with separator
    key_str = f"{url}::{script}"
    return hashlib.sha256(key_str.encode()).hexdigest()

def _load_existing_keys(file_path: str | None = None) -> set:
    """Load uniqueness keys for existing test cases."""
    if not file_path:
        file_path = UI_TEST_FILE
        
    if not Path(file_path).exists():
        return set()
        
    wb = openpyxl.load_workbook(file_path)
    if UI_TEST_SHEET not in wb.sheetnames:
        wb.close()
        return set()
        
    ws = wb[UI_TEST_SHEET]
    if ws.max_row <= 1:
        wb.close()
        return set()

    headers = [str(cell.value or '').lower() for cell in ws[1]]
    
    # Find required column indices
    try:
        url_idx = headers.index('url')
        # Try both 'validate_script' and 'script'
        try:
            script_idx = headers.index('validate_script')
        except ValueError:
            try:
                script_idx = headers.index('script')
            except ValueError:
                # No valid script column found
                wb.close()
                return set()
    except ValueError:
        # No URL column found
        wb.close()
        return set()
    
    existing_keys = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[url_idx] is not None and row[script_idx] is not None:
            test_case = {
                'url': row[url_idx],
                'validate_script': row[script_idx]  # Use validate_script for key generation
            }
            existing_keys.add(_generate_test_key(test_case))
    
    wb.close()
    return existing_keys

async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Insert UI test cases with duplicate prevention and run tests.
    
    Args:
        test_cases: List of test cases to insert, each containing:
            - module: Test module/group
            - description: Test description
            - url: Page URL to test
            - script: Playwright script to run
            - expected_result: Expected outcome
            
    Returns:
        Dict with test execution results after insertion.
        
    Raises:
        DuplicateTestError: If any test case already exists
        ValueError: For invalid/missing required fields
    """
    test_cases = args.get('test_cases', [])
    
    # Required fields for each test case
    required_fields = {
        'module', 'description', 'url', 'validate_script',
        'expected_result'
    }
    
    # Define column headers
    headers = [
        'module',
        'description',
        'url',
        'validate_script',  # Changed from 'script' to match existing UI test structure
        'expected_result',
        'actual_result',
        'status',
        'last_run',
        'result'
    ]
    
    # Load or create workbook and sheet
    file_path = Path(UI_TEST_FILE)
    if not file_path.exists():
        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is not None:
            ws.title = UI_TEST_SHEET
        else:
            wb.create_sheet(UI_TEST_SHEET)
            ws = wb[UI_TEST_SHEET]
    else:
        wb = openpyxl.load_workbook(file_path)
        if UI_TEST_SHEET not in wb.sheetnames:
            ws = wb.create_sheet(UI_TEST_SHEET)
        else:
            ws = wb[UI_TEST_SHEET]
    
    # Ensure we have headers
    if ws.max_row <= 1:
        ws.append(headers)
    
    # Get existing test case keys
    existing_keys = _load_existing_keys(str(file_path))
    print(f"Initial existing keys: {existing_keys}")
    
    # Keep track of keys as we validate and insert
    seen_keys = existing_keys.copy()
    
    # Validate all test cases before insertion
    for test in test_cases:
        # Check required fields
        missing = required_fields - set(test.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
            
        # Check for duplicates
        test_key = _generate_test_key(test)
        print(f"Generated key: {test_key}")
        print(f"Seen keys: {seen_keys}")
        if test_key in seen_keys:
            url = str(test.get('url', '')).strip()
            raise DuplicateTestError(f"Duplicate test case for URL: {url}")
        seen_keys.add(test_key)
    
    # All validation passed, insert test cases
    headers = [str(cell.value).lower() for cell in ws[1]]
    
    for test in test_cases:
        # Prepare row data
        row_data = []
        for header in headers:
            if header == 'status':
                row_data.append('active')  # Default status
            elif header == 'last_run':
                row_data.append(datetime.now().strftime('%Y-%m-%d %H:%M'))
            elif header == 'result':
                row_data.append('')  # Empty initial result
            elif header == 'actual_result':
                row_data.append('')  # Empty actual values
            else:
                row_data.append(test.get(header, ''))
        
        ws.append(row_data)
    
    # Save changes
    wb.save(file_path)
    wb.close()
    
    # Run tests and return results 
    return await run_excel_suite.run({
        'file': UI_TEST_FILE,
        'sheet': UI_TEST_SHEET
    })