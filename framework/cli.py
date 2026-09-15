"""Optional server-local CSV argument shared by both launch methods."""
from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class StartupCSVOptions:
    path: Path | None
    load_all: bool = False

# the value is probably the path input into the CLI cmd line
def validate_csv_path(value):
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() != '.csv':
        raise ValueError('The startup file must have a .csv extension.')
    if not path.is_file():
        raise ValueError(f'CSV file not found or not a regular file: {path}')
    return path


def startup_csv_options():
    # Only inspect application arguments, never a hosting process's unrelated argv.
    if Path(sys.argv[0]).name not in {'Load CSV.py', 'Load CSV_2.py'}:
        return StartupCSVOptions(None)
    arguments = sys.argv[1:]
    load_all = arguments.count('--load-all') == 1
    if arguments.count('--load-all') > 1:
        raise ValueError('Supply --load-all only once.')
    positional = [value for value in arguments if value != '--load-all']
    unknown = [value for value in positional if value.startswith('--')]
    if unknown:
        raise ValueError(f'Unknown application argument: {unknown[0]}')
    if len(positional) > 1:
        raise ValueError('Supply one CSV path; quote paths containing spaces.')
    if load_all and not positional:
        raise ValueError('--load-all requires a CSV path after Streamlit\'s -- separator.')
    path = validate_csv_path(positional[0]) if positional else None
    return StartupCSVOptions(path, load_all)


def startup_csv_argument():
    """Compatibility view used by callers that need only the optional path."""
    return startup_csv_options().path
