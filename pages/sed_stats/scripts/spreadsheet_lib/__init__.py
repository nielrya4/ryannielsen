"""
Spreadsheet library for Antioch apps.

Components:
    TabulatorSheet    - editable data grid backed by the Tabulator JS library
    SpreadsheetUpload - file picker that parses csv/xls/xlsx into row dicts
    parse_file        - parse a filename + content pair into row dicts
    rows_to_csv       - turn row dicts back into CSV text
"""
from .grid import TabulatorSheet
from .upload import SpreadsheetUpload
from .importers import (parse_file, parse_csv, parse_xls, parse_xlsx,
                        rows_to_csv, SUPPORTED_EXTENSIONS)

__all__ = [
    'TabulatorSheet',
    'SpreadsheetUpload',
    'parse_file',
    'parse_csv',
    'parse_xls',
    'parse_xlsx',
    'rows_to_csv',
    'SUPPORTED_EXTENSIONS',
]

__version__ = '0.1.0'