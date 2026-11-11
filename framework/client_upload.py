"""Bounded disk staging for single-use client CSV launches."""
import asyncio
from contextlib import aclosing
import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
import secrets
import shutil
import tempfile
import threading
import time
import uuid

from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse

from framework import data
from framework.admin_server import protect

TOKEN_PARAM = 'client_csv'
TTL = 600
UPLOAD_TIMEOUT = 300
OWNER_HEADER = 'x-dashboard-client-owner'


def owner_hash(value):
    if re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise ValueError('Invalid client ownership credential. Use the updated client script.')
    return hashlib.sha256(bytes.fromhex(value)).digest()


class UploadStopped(Exception):
    pass



@dataclass(frozen=True)
class Upload:
    path: Path
    name: str
    parquet: bool
    size: int
    expires: float
    owner: bytes | None = None


class Staging:
    def __init__(self, directory, limit):
        self.directory = directory
        self.limit = limit
        self.pending = {}
        self.inflight = {}
        self.claimed = {}
        self.discarded = {}
        self.receiving = 0
        self.bytes = 0
        self.lock = threading.Lock()

    def _expire(self):
        for token, upload in list(self.pending.items()):
            if upload.expires <= time.monotonic():
                self.discarded[upload.path] = upload.size
                del self.pending[token]
        for path, size in list(self.discarded.items()):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # A Windows scanner can briefly hold the file open.
                continue
            self.bytes -= size
            del self.discarded[path]

    def sweep(self):
        with self.lock:
            self._expire()
            self.directory.touch()
        remove_stale_directories(self.directory.parent)

    def reserve(self, size, owner=None, cancelled=None):
        with self.lock:
            self._expire()
            if (self.receiving >= 2 or self.receiving + len(self.pending) + len(self.discarded) >= 8
                    or self.bytes + size > 2 * self.limit):
                return False
            self.receiving += 1
            self.bytes += size
            if owner is not None:
                self.inflight[cancelled] = owner
            return True

    def finish(self, size, upload=None, cancelled=None, path=None):
        with self.lock:
            self.receiving -= 1
            if cancelled is not None:
                self.inflight.pop(cancelled, None)
            if upload is None or (cancelled is not None and cancelled.is_set()):
                if path is not None:
                    self.discarded[path] = size
                    self._expire()
                else:
                    self.bytes -= size
                return None
            token = secrets.token_urlsafe(32)
            self.pending[token] = upload
            return token

    def claim(self, token, session_id, runtime_id=None):
        with self.lock:
            self._expire()
            upload = self.pending.get(token)
            if upload is None or upload.expires <= time.monotonic():
                return None
            if runtime_id in self.claimed or (upload.owner is not None and runtime_id is None):
                return None
            destination = data.session_directory(session_id) / upload.path.name
            upload.path.replace(destination)
            del self.pending[token]
            self.bytes -= upload.size
            if upload.owner is not None:
                self.claimed[runtime_id] = (upload.owner, session_id)
            return destination, upload.name, upload.parquet

    def cancel_group(self, owner):
        # Claim, upload registration and revocation share this lock.
        with self.lock:
            cancelled = 0
            self._expire()
            for signal, digest in self.inflight.items():
                if digest == owner and not signal.is_set():
                    signal.set()
                    cancelled += 1
            for token, upload in list(self.pending.items()):
                if upload.owner == owner:
                    self.discarded[upload.path] = upload.size
                    del self.pending[token]
                    cancelled += 1
            self._expire()
            return cancelled, {sid: private for sid, (digest, private) in self.claimed.items()
                               if digest == owner}

    def reap_sessions(self, adapter):
        adapter.reap()
        with self.lock:
            for sid, (_, private) in list(self.claimed.items()):
                if sid not in adapter.pending and adapter.manager.get_session_info(sid) is None:
                    if adapter.remove_files({'private_id': private}):
                        del self.claimed[sid]



staging = None


def remove_stale_directories(root):
    # Keep live processes isolated. Their leases are renewed by the periodic sweep.
    for directory in root.glob('server-*'):
        try:
            if time.time() - directory.stat().st_mtime > 3600:
                shutil.rmtree(directory, ignore_errors=True)
        except FileNotFoundError:
            pass


def start_staging():
    root = data.ROOT / '.client-uploads'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    protect(root, directory=True)
    remove_stale_directories(root)
    directory = Path(tempfile.mkdtemp(prefix='server-', dir=root))
    return Staging(directory, data.MAX_UPLOAD_MB * 1024**2)


def response(status, **payload):
    return JSONResponse(payload, status_code=status, headers={'Cache-Control': 'no-store'})


def controller():
    from streamlit.runtime import get_instance
    from framework.admin_runtime import shared_adapter

    return shared_adapter(get_instance())


async def stop_sessions(request):
    if request.headers.get('origin'):
        return response(403, error='Use the client script to stop sessions.')
    try:
        owner = owner_hash(request.headers.get(OWNER_HEADER, ''))
    except ValueError as error:
        return response(400, error=str(error))
    store = staging
    if store is None:
        return response(503, error='Client session control is unavailable.')
    try:
        adapter = controller()
    except RuntimeError:
        return response(503, error='Client session control is unavailable.')
    cancelled, sessions = store.cancel_group(owner)
    stopped = terminating = failed = 0
    for sid, private in sessions.items():
        try:
            result = adapter.terminate(sid, private)
            if result['state'] == 'terminated':
                stopped += 1
            else:
                terminating += 1
        except KeyError:
            continue  # Already ended or expired.
        except Exception:
            adapter.audit.exception('Client session termination failed')
            failed += 1
    store.reap_sessions(adapter)
    counts = dict(stopped=stopped, cancelled=cancelled, terminating=terminating)
    if failed:
        return response(503, **counts, error=f'Could not stop {failed} session(s). Retry or contact the server operator.')
    return response(200, **counts)


async def upload_chunks(request, cancelled):
    # Wake a stalled receiver immediately on stop. File writes and validation
    # finish before releasing their reservation, including on Windows.
    stream = request.stream()
    stop = asyncio.create_task(cancelled.wait())
    try:
        while True:
            chunk = asyncio.create_task(anext(stream))
            try:
                await asyncio.wait((chunk, stop), return_when=asyncio.FIRST_COMPLETED)
                if cancelled.is_set():
                    raise UploadStopped
                yield chunk.result()
            except StopAsyncIteration:
                return
            finally:
                if not chunk.done():
                    chunk.cancel()
                await asyncio.gather(chunk, return_exceptions=True)
    finally:
        stop.cancel()
        await asyncio.gather(stop, return_exceptions=True)


async def upload_csv(request):
    store = staging
    if store is None:
        return response(503, error='CSV staging is unavailable.')
    # Browser cross-origin submissions are unnecessary for the Windows client.
    if request.headers.get('origin'):
        return response(403, error='Use the client script to submit the CSV.')
    try:
        header = request.headers.get(OWNER_HEADER)
        owner = owner_hash(header) if header is not None else None
    except ValueError as error:
        return response(400, error=str(error))
    name = request.query_params.get('filename', '')
    parquet = request.query_params.get('parquet', 'false').lower()
    if (not name or len(name) > 255 or PureWindowsPath(name).name != name
            or any(ord(c) < 32 or c in '/\\:*?"<>|' for c in name)
            or Path(name).suffix.lower() != '.csv' or parquet not in {'true', 'false'}):
        return response(400, error='Supply a CSV filename and parquet=true or false.')
    length = request.headers.get('content-length', '')
    if not length.isascii() or not length.isdecimal() or len(length) > 20:
        return response(411, error='Send the CSV with an explicit Content-Length.')
    size = int(length)
    if size == 0:
        return response(400, error='The CSV is empty.')
    if size > store.limit:
        return response(413, error=f'CSV exceeds the {data.MAX_UPLOAD_MB} MB upload limit.')
    cancelled = asyncio.Event()
    if not store.reserve(size, owner, cancelled):
        return response(429, error='CSV staging is full. Wait for another upload to finish or expire.')
    path = store.directory / f'{uuid.uuid4().hex}.csv'
    retained = None
    try:
        received = 0
        async with asyncio.timeout(UPLOAD_TIMEOUT):
            with path.open('xb') as output:
                async with aclosing(upload_chunks(request, cancelled)) as chunks:
                    async for chunk in chunks:
                        received += len(chunk)
                        if received > size:
                            return response(400, error='CSV body exceeds its declared length.')
                        if chunk:
                            await run_in_threadpool(output.write, chunk)
        if received != size:
            return response(400, error='CSV upload ended before the declared length.')
        await run_in_threadpool(data.validate_source, path)
        retained = Upload(path, name, parquet == 'true', size, time.monotonic() + TTL, owner)
    except UploadStopped:
        return response(409, error='Upload cancelled by the client stop command.')
    except (ClientDisconnect, TimeoutError):
        return response(408, error='CSV upload was interrupted or timed out.')
    except (ValueError, csv.Error) as error:
        return response(400, error=f'Invalid CSV: {error}')
    except OSError:
        return response(503, error='Unable to store the CSV. Check server disk capacity.')
    finally:
        token = store.finish(size, retained, cancelled, path)
    if token is None:
        return response(409, error='Upload cancelled by the client stop command.')
    return response(201, launch_url=f'./?{TOKEN_PARAM}={token}', expires_in=TTL)
