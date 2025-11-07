"""Unified test suite runner that routes to domain-specific runners based on Excel file name."""
from typing import Dict, Any
from pathlib import Path
import asyncio

class Error(Exception):
    """Base error class."""
    pass

class UserError(Error):
    """User input error."""
    pass

from . import api_from_excel, test_from_excel

async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Run a test suite from Excel, routing to the appropriate domain runner.
    
    Args:
        file: Path to Excel file (./data/[domain]_tests.xlsx)
        sheet: Sheet name (optional, defaults to [domain]_tests)
        
    Returns:
        Dict with test execution summary:
        {
            "passed": int,
            "failed": int,
            "skipped": int,
            "domain": str,  # api, ui, or db
            "details": List[Dict]  # Full test results
        }
    """
    file_path = args.get('file')
    if not file_path:
        raise UserError("file parameter is required")
    
    path = Path(file_path)
    if not path.exists():
        raise UserError(f"File not found: {file_path}")

    # Detect domain from filename
    file_name = path.name.lower()
    if file_name.startswith('api_'):
        domain = 'api'
    elif file_name.startswith('ui_'):
        domain = 'ui'
    elif file_name.startswith('db_'):
        domain = 'db'
    else:
        raise UserError(f"Cannot detect domain from filename: {file_name}. Must start with api_, ui_, or db_")

    # Default sheet name based on domain if not provided
    sheet = args.get('sheet', f'{domain}_tests')

    # Route to appropriate runner
    try:
        if domain == 'api':
            result = await api_from_excel.run({'file': str(path), 'sheet': sheet})
            return {
                'passed': result.get('passed', 0),
                'failed': result.get('failed', 0),
                'skipped': 0,  # API tests don't support skip yet
                'domain': 'api',
                'details': result.get('results', [])
            }
        elif domain == 'ui':
            result = await test_from_excel.run({'file': str(path), 'sheet': sheet})
            return {
                'passed': sum(1 for r in result.get('results', []) if r.get('success')),
                'failed': sum(1 for r in result.get('results', []) if not r.get('success')),
                'skipped': 0,  # UI tests don't support skip yet
                'domain': 'ui',
                'details': result.get('results', [])
            }
        elif domain == 'db':
            # TODO: DB test runner not implemented yet
            return {
                'passed': 0,
                'failed': 0,
                'skipped': 0,
                'domain': 'db',
                'error': 'DB test runner not implemented yet',
                'details': []
            }
        else:
            raise UserError(f"Unknown domain: {domain}")

    except Exception as e:
        return {
            'passed': 0,
            'failed': 1,
            'skipped': 0,
            'domain': domain,
            'error': str(e),
            'details': []
        }