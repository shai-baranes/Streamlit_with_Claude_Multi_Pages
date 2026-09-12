"""Optional server-local CSV argument shared by both launch methods."""
from pathlib import Path
import sys


def validate_csv_path(value):
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() != '.csv':
        raise ValueError('The startup file must have a .csv extension.')
    if not path.is_file():
        raise ValueError(f'CSV file not found or not a regular file: {path}')
    return path


def startup_csv_argument():
    # Only inspect application arguments, never a hosting process's unrelated argv.
    if Path(sys.argv[0]).name not in {'Load CSV.py', 'Load CSV_2.py'}:
        return None
    if len(sys.argv) > 2:
        raise ValueError('Supply one CSV path; quote paths containing spaces.')
    return validate_csv_path(sys.argv[1]) if len(sys.argv) == 2 else None
