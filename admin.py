"""Local CLI; use SSH to execute this on the dashboard server."""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
from framework.admin_server import credential_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8502)
    parser.add_argument('--credential-file', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('credential-path')
    sessions = commands.add_parser('sessions').add_subparsers(dest='action', required=True)
    listing = sessions.add_parser('list')
    listing.add_argument('--json', action='store_true')
    sessions.add_parser('inspect').add_argument('id')
    terminate = sessions.add_parser('terminate')
    terminate.add_argument('id')
    terminate.add_argument('--yes', action='store_true')
    args = parser.parse_args(argv)
    path = args.credential_file or credential_path(args.port)
    if args.command == 'credential-path':
        print(path)
        return 0
    try:
        credential = json.loads(path.read_text())
        # Credentials cannot redirect the CLI to transmit a token off-machine.
        url = f'http://127.0.0.1:{args.port}'
        if args.action == 'terminate':
            if not args.yes and input(f'Terminate {args.id} and discard its data? [y/N] ').lower() != 'y':
                return 1
            body = json.dumps({'id': args.id}).encode()
            endpoint = '/terminate'
        else:
            body, endpoint = None, '/sessions'
        request = Request(url + endpoint, data=body, headers={'Authorization': 'Bearer ' + credential['token'], 'Content-Type':'application/json'})
        # Administration credentials must never travel through an environment HTTP proxy.
        with build_opener(ProxyHandler({})).open(request, timeout=20) as response:
            data = json.load(response)
        if args.action == 'inspect':
            data = next((s for s in data['sessions'] if s['id'] == args.id), None)
            if data is None:
                print('Session not found.', file=sys.stderr)
                return 4
        if args.action == 'list' and not args.json:
            for s in data['sessions']:
                print(f"{s['id']}  {s['state']}  {s.get('address', 'unknown')}  frame={s['frame_bytes']/1048576:.1f} MiB  {s.get('dataset') or '(empty)'}")
        else:
            print(json.dumps(data, indent=2))
        return 5 if data.get('state') == 'terminating' else 0
    except HTTPError as error:
        print(f'Administration request failed: HTTP {error.code}', file=sys.stderr)
        return {401:3, 403:3, 404:4}.get(error.code, 2)
    except (OSError, ValueError, KeyError, URLError) as error:
        print(f'Administration unavailable: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
