"""Portable launcher; debug does not enable sample data or weaken isolation."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from framework.config import MAX_UPLOAD_MB

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true', help='Foreground macOS/development logging')
    parser.add_argument('--sample', action='store_true', help='Offer explicit sample-data button')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--address', default='0.0.0.0')
    args = parser.parse_args()
    env = dict(os.environ, DASHBOARD_SAMPLE='1' if args.sample else '0')
    command = [sys.executable, '-m', 'streamlit', 'run', 'Load CSV.py',
               f'--server.port={args.port}', f'--server.address={args.address}',
               '--server.headless=true', f'--server.maxUploadSize={MAX_UPLOAD_MB}',
               '--server.enableXsrfProtection=true', '--server.enableCORS=true',
               '--logger.level=' + ('debug' if args.debug else 'info')]
    return subprocess.call(command, cwd=Path(__file__).parent, env=env)

if __name__ == '__main__':
    raise SystemExit(main())
