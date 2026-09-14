"""Loopback-only administration transport, authenticated by an OS-protected token."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def credential_path(port):
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    return base / '.engineering-dashboard-admin' / str(port) / 'credential.json'


def protect(path, directory=False):
    if os.name == 'nt':
        account = subprocess.check_output(['whoami'], text=True).strip()
        grant = '(OI)(CI)F' if directory else 'F'
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'{account}:{grant}',
                        f'*S-1-5-18:{grant}'], check=True, capture_output=True)
    else:
        path.chmod(0o700 if directory else 0o600)


class AdminServer:
    def __init__(self, port):
        self.token = secrets.token_urlsafe(32)
        self.adapter = None
        self.error = 'Streamlit runtime is starting.'
        self.path = credential_path(port)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        protect(self.path.parent, True)
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(20)

            def log_message(self, *_):
                pass  # Never log bearer tokens or request bodies.

            def send(self, code, data, content_type='application/json'):
                payload = data.encode() if isinstance(data, str) else json.dumps(data).encode()
                self.send_response(code)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(payload)

            def authorized(self):
                expected = f'127.0.0.1:{owner.http.server_port}'
                if self.headers.get('Host') != expected:
                    self.send(403, {'error': 'Use the loopback address 127.0.0.1.'})
                    return False
                origin = self.headers.get('Origin')
                if origin and origin != f'http://{expected}':
                    self.send(403, {'error': 'Invalid origin.'})
                    return False
                if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + owner.token):
                    self.send(401, {'error': 'Administration credential required.'})
                    return False
                if owner.adapter is None:
                    self.send(503, {'error': owner.error})
                    return False
                return True

            def do_GET(self):
                if self.path in ('/', '/admin.js', '/admin.css'):
                    name, kind = {'/': ('admin.html', 'text/html; charset=utf-8'), '/admin.js': ('admin.js', 'text/javascript'), '/admin.css': ('admin.css', 'text/css')}[self.path]
                    self.send(200, (Path(__file__).parent / 'admin_assets' / name).read_text(), kind)
                    return
                if not self.authorized():
                    return
                try:
                    if self.path != '/sessions':
                        self.send(404, {'error': 'Unknown endpoint.'})
                    else:
                        self.send(200, owner.adapter.call('snapshot'))
                except Exception:
                    owner.audit.exception('snapshot failed')
                    self.send(503, {'error': 'Runtime inspection unavailable; see server admin log.'})

            def do_POST(self):
                if not self.authorized():
                    return
                if self.path != '/terminate':
                    self.send(404, {'error': 'Unknown endpoint.'})
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 1024:
                        raise ValueError('Invalid request size')
                    sid = json.loads(self.rfile.read(size))['id']
                    if not isinstance(sid, str) or len(sid) > 128:
                        raise ValueError('Invalid session id')
                    result = owner.adapter.call('terminate', sid)
                    self.send(202 if result['state'] == 'terminating' else 200, result)
                except KeyError:
                    self.send(404, {'error': 'Session not found.'})
                except (ValueError, TypeError):
                    self.send(400, {'error': 'Invalid request.'})
                except Exception:
                    owner.audit.exception('termination failed')
                    self.send(503, {'error': 'Termination unavailable; inspect status before retrying.'})
        self.http = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.http.daemon_threads = True
        self.path.write_text(json.dumps({'url': f'http://127.0.0.1:{self.http.server_port}', 'token': self.token}))
        protect(self.path)
        self.audit = logging.getLogger(f'dashboard.admin.{port}')
        handler = RotatingFileHandler(self.path.parent / 'admin.log', maxBytes=1024*1024, backupCount=3)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.audit.addHandler(handler)
        self.audit.setLevel(logging.INFO)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.path.unlink(missing_ok=True)
        for handler in list(self.audit.handlers):
            handler.close()
            self.audit.removeHandler(handler)
