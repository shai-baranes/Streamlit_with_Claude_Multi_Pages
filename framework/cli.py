"""Optional server-local CSV argument shared by both launch methods."""
from dataclasses import dataclass
from pathlib import Path
import sys
import argparse


@dataclass(frozen=True)
class StartupCSVOptions:
    path: Path | None
    load_all: bool = False
    auto_apply: bool = False
    parquet: bool = False

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
    if Path(sys.argv[0]).name not in {'Load CSV.py', 'Load CSV_2.py', 'dashboard_server.py'}:
        return StartupCSVOptions(None)
    parser = _ApplicationParser(add_help=False, allow_abbrev=False)
    add_csv_arguments(parser)
    parser.add_argument('--load-all', action='store_true')
    args = parser.parse_args(sys.argv[1:])
    if sys.argv[1:].count('--load-all') > 1:
        raise ValueError('Supply --load-all only once.')
    if args.csv_path and args.csv_file:
        raise ValueError('Supply either CSV_PATH or --csv_file, not both.')
    if args.load_all and args.csv_file:
        raise ValueError('--load-all cannot be combined with --csv_file.')
    if args.load_all and not args.csv_path:
        raise ValueError('--load-all requires a CSV path after Streamlit\'s -- separator.')
    source = args.csv_file or args.csv_path
    return StartupCSVOptions(validate_csv_path(source) if source else None,
                             args.load_all, args.csv_file is not None, args.parquet)


class _ApplicationParser(argparse.ArgumentParser):
    def error(self, message):
        # In-app argument errors must leave the upload UI available.
        raise ValueError(message)


def parse_boolean(value):
    if value.lower() not in {'true', 'false'}:
        raise argparse.ArgumentTypeError('Expected true or false.')
    return value.lower() == 'true'


def add_csv_arguments(parser):
    """Keep launcher and direct Streamlit argument names/defaults identical."""
    parser.add_argument('csv_path', nargs='?', help='Server-local CSV to stage in each new session')
    parser.add_argument('--csv_file', metavar='PATH', help='Automatically apply fixed columns and the full Seconds interval')
    parser.add_argument('--parquet', type=parse_boolean, default=False, metavar='true|false',
                        help='Initial experimental Parquet checkbox value (default: false)')


def startup_csv_argument():
    """Compatibility view used by callers that need only the optional path."""
    return startup_csv_options().path
