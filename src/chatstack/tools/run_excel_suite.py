"""Unified test suite router that routes to domain-specific runners based on Excel file name prefix."""
from typing import Dict, Any
from pathlib import Path
import asyncio

from . import api_from_excel, test_from_excel, db_from_excel

# Map domains to their runner functions
DOMAIN_RUNNERS = {
    'api': api_from_excel.run,
    'ui': test_from_excel.run,
    'db': db_from_excel.run
}

async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Route test execution to appropriate domain runner based on file prefix.
    
    Args:
        file: Path to Excel file (must start with api_, ui_, or db_)
        sheet: Sheet name (optional)
        
    Returns:
        Dict with standardized test results:
        {
            "passed": int,
            "failed": int,
            "skipped": int,
            "results": List[Dict]
        }
        
    Raises:
        ValueError: If file path not provided or invalid domain prefix
    """
    if 'file' not in args:
        raise ValueError("file parameter is required")
    
    file_path = Path(args['file'])
    if not file_path.exists():
        raise ValueError(f"File not found: {file_path}")

    # Extract prefix for domain routing
    file_name = file_path.name.lower()
    
    # Strict prefix matching
    if file_name.startswith('api_'):
        domain = 'api'
    elif file_name.startswith('ui_'):
        domain = 'ui'
    elif file_name.startswith('db_'):
        domain = 'db'
    else:
        raise ValueError(
            f"Invalid file prefix: {file_name}. "
            f"Must start with api_, ui_, or db_"
        )

    # Route to appropriate runner
    runner = DOMAIN_RUNNERS[domain]
    result = await runner(args)
    
    # Ensure standardized return format
    return {
        'passed': result.get('passed', 0),
        'failed': result.get('failed', 0),
        'skipped': result.get('skipped', 0),
        'results': result.get('results', [])
    }