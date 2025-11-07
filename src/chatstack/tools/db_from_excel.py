"""Database test runner that executes tests from Excel using db_query tool."""
from typing import Dict, Any, List
from pathlib import Path
import asyncio
import openpyxl
from datetime import datetime

from .db_query import run as run_query

def _compare_values(actual_str: str, expected_str: str) -> bool:
    """Compare actual and expected values with limited operator support.
    
    Supported patterns:
    - Exact match: Direct string comparison
    - Operators: Only =, >, < (no >=, <=, !=)
    - Special cases:
        '*': Existence check (always true if there's a result)
        '=0': Zero results check
    
    All other patterns will return False.
    NOTE: Additional operators/patterns require explicit review and approval.
    """
    if not expected_str:
        return False

    expected_str = str(expected_str).strip()
    actual_str = str(actual_str).strip()
    
    # Special cases
    if expected_str == '*':
        return True
        
    # Handle numeric comparisons (limited to =, >, <)
    if expected_str.startswith(('>', '<', '=')):
        op = expected_str[0]
        if op not in ('>', '<', '='):
            return False
            
        try:
            exp_num = float(expected_str[1:].strip())
            act_num = float(actual_str)
            
            if op == '>':
                return act_num > exp_num
            elif op == '<':
                return act_num < exp_num
            elif op == '=':
                return act_num == exp_num
        except ValueError:
            return False
            
    # Direct string comparison
    return actual_str == expected_str

async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Run database tests from Excel file.
    
    Args:
        file: Path to Excel file containing tests
        sheet: Sheet name with test cases
        
    Returns:
        Dict with results:
        {
            "passed": int,
            "failed": int,
            "skipped": int,
            "results": List[Dict] - Detailed test results
        }
    """
    if 'file' not in args:
        raise ValueError("file parameter is required")
        
    file_path = Path(args['file'])
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
        
    sheet_name = args.get('sheet', 'db_tests')
    
    # Load workbook
    wb = openpyxl.load_workbook(file_path, data_only=True)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet {sheet_name} not found in {file_path}")
    
    ws = wb[sheet_name]
    
    # Get headers
    headers = [str(cell.value or '').lower() for cell in ws[1]]
    
    # Required columns matching other test runners
    required_cols = ['module', 'description', 'query', 'expected_field', 
                    'expected_value', 'status']
    missing_cols = [col for col in required_cols if col not in headers]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
        
    # Initialize results
    results = []
    passed = 0
    failed = 0
    skipped = 0
    
    # Process each test case
    for row in ws.iter_rows(min_row=2, values_only=True):
        row_data = {k: (str(v) if v is not None else '') for k, v in zip(headers, row)}
        
        # Skip inactive tests
        if str(row_data.get('status', '')).lower() != 'active':
            skipped += 1
            continue

        # Initialize test result
        test_result = {
            'module': row_data['module'],
            'description': row_data['description'],
            'query': row_data['query'],
            'expected_field': row_data['expected_field'],
            'expected_value': row_data['expected_value'],
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'error': None
        }
        
        try:
            # Execute query using db_query tool
            query_result = await run_query({
                'query': row_data['query']
            })
            
            if not query_result.get('success'):
                raise Exception(query_result.get('error', 'Query failed'))
            
            rows = query_result.get('rows', [])
            test_result['actual_rows'] = len(rows)
            
            # No results = fail unless we expect zero results
            if not rows:
                if row_data['expected_value'] in ('0', '=0'):
                    test_result['success'] = True
                    test_result['actual_value'] = '0'
                    passed += 1
                else:
                    test_result['error'] = 'No results returned'
                    test_result['actual_value'] = 'null'
                    failed += 1
                results.append(test_result)
                continue

            # Get actual value for comparison
            if row_data['expected_field'] == '*':
                # Just checking query succeeds
                test_result['success'] = True
                test_result['actual_value'] = 'success'
                passed += 1
            else:
                # Extract value from results
                field = row_data['expected_field']
                if field not in rows[0]:
                    test_result['error'] = f"Field {field} not found in results"
                    test_result['actual_value'] = 'field_missing'
                    failed += 1
                    results.append(test_result)
                    continue
                
                actual_value = str(rows[0][field])
                test_result['actual_value'] = actual_value
                
                # Compare values
                test_result['success'] = _compare_values(
                    actual_value,
                    row_data['expected_value']
                )
                
                if test_result['success']:
                    passed += 1
                else:
                    failed += 1
                    test_result['error'] = (
                        f'Value mismatch. Expected: {row_data["expected_value"]}, '
                        f'Got: {actual_value}'
                    )
                        
        except Exception as e:
            failed += 1
            test_result['success'] = False
            test_result['error'] = str(e)
            test_result['actual_value'] = 'error'
            
        results.append(test_result)
    
    wb.close()
    
    return {
        'passed': passed,
        'failed': failed,
        'skipped': skipped,
        'results': results
    }