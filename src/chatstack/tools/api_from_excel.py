"""API test orchestrator that reads from Excel and uses api_call tool for validation."""
from typing import Any, Dict, List, Optional
import openpyxl
from pathlib import Path

class Error(Exception):
    """Base error class."""
    pass

class UserError(Error):
    """User input error."""
    pass

async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Run API tests from Excel file."""
    file_path = args.get('file')
    sheet_name = args.get('sheet', 'api_tests')
    
    if not file_path:
        raise UserError("file parameter is required")
        
    path = Path(file_path)
    if not path.exists():
        raise UserError(f"File not found: {file_path}")
        
    wb = openpyxl.load_workbook(path)
    if sheet_name not in wb.sheetnames:
        raise UserError(f"Sheet '{sheet_name}' not found in {file_path}")
        
    ws = wb[sheet_name]
    
    # Get headers from first row
    headers = [str(cell.value or '').lower() for cell in next(ws.rows)]
    required_cols = {'method', 'url', 'expected_field', 'expected_value', 'status'}
    missing = required_cols - set(headers)
    if missing:
        raise UserError(f"Missing required columns: {', '.join(missing)}")
        
    results = []
    for row in list(ws.rows)[1:]:  # Skip header row
        test_case = {headers[i]: cell.value for i, cell in enumerate(row)}
        if not test_case.get('method') or not test_case.get('url'):  # Skip empty rows
            continue
            
        # Prepare API call arguments
        api_args = {
            'method': str(test_case['method']),
            'url': str(test_case['url']),
            'body': test_case.get('body'),
            'headers': test_case.get('headers'),
            'expected_status': int(str(test_case['status'])) if test_case.get('status') else None
        }
        
        try:
            # Import here to avoid circular imports
            from .api_call import run as api_call_run
            result = await api_call_run(api_args)
            success = True
            
            # Validate expected field/value if specified
            if test_case.get('expected_field') and test_case.get('expected_value') is not None:
                field_val = result.get('body', {}).get(str(test_case['expected_field']))
                success = str(field_val) == str(test_case['expected_value'])
                if not success:
                    result['error'] = f"Expected {test_case['expected_field']}={test_case['expected_value']}, got {field_val}"
            
            results.append({
                'test_case': test_case,
                'success': success,
                'result': result
            })
            
        except Exception as e:
            results.append({
                'test_case': test_case,
                'success': False,
                'error': str(e)
            })
            
    return {
        'total': len(results),
        'passed': sum(1 for r in results if r['success']),
        'failed': sum(1 for r in results if not r['success']),
        'results': results
    }