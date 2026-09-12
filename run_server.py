"""Portable launcher; debug does not enable sample data or weaken isolation."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from framework.config import MAX_UPLOAD_MB
from framework.cli import validate_csv_path

def main():
    parser = argparse.ArgumentParser()
    # Optional positional path preserves the existing no-argument launch behavior.
    parser.add_argument('csv_path', nargs='?', help='Server-local CSV to stage in each new session')
    parser.add_argument('--debug', action='store_true', help='Foreground macOS/development logging')
    parser.add_argument('--sample', action='store_true', help='Offer explicit sample-data button')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--address', default='0.0.0.0')
    args = parser.parse_args()
    try:
        csv_path = validate_csv_path(args.csv_path) if args.csv_path else None
    except ValueError as error:
        parser.error(str(error))
    env = dict(os.environ, DASHBOARD_SAMPLE='1' if args.sample else '0')
    command = [sys.executable, '-m', 'streamlit', 'run', 'Load CSV.py',
               f'--server.port={args.port}', f'--server.address={args.address}',
               '--server.headless=true', f'--server.maxUploadSize={MAX_UPLOAD_MB}',
               '--server.enableXsrfProtection=true', '--server.enableCORS=true',
               '--logger.level=' + ('debug' if args.debug else 'info')]
    # Resolve before changing cwd and forward after Streamlit's argument separator.
    if csv_path is not None:
        command.extend(['--', str(csv_path)])
    return subprocess.call(command, cwd=Path(__file__).parent, env=env)

if __name__ == '__main__':
    raise SystemExit(main())
