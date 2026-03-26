"""
Loads raw provider records from dirty_providers.json.
"""

import json
from pathlib import Path

_JSON_PATH = Path(__file__).parent / "dirty_providers.json"


def load_dirty_records(path: str = None) -> list:
    """Load raw provider records from a JSON file.

    Args:
        path: Optional override path. Defaults to dirty_providers.json
              in the same directory as this file.

    Returns:
        List of provider dicts. Fields with JSON null become Python None.
        Records with a '_comment' key have that key stripped out.
    """
    source = Path(path) if path else _JSON_PATH
    with open(source, encoding="utf-8") as f:
        records = json.load(f)
    # Strip metadata-only keys that aren't data fields
    return [{k: v for k, v in rec.items() if k != "_comment"} for rec in records]
