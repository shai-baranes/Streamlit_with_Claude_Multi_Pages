"""Version-sensitive Streamlit administration, confined to its event loop."""
import concurrent.futures
import ipaddress
import logging
import secrets
import threading
import shutil
import time
import uuid
from pathlib import Path
from dataclasses import dataclass

import pandas as pd
import psutil

from framework.config import ROOT


_adapter_lock = threading.Lock()
_adapter = None
IDLE_MINUTES = (5, 15, 30, 60)
DEFAULT_IDLE_MINUTES = 15


@dataclass
class BrowserActivity:
    token: str
    last_activity: float


def shared_adapter(runtime, audit=None):
    """Use one termination queue for both dashboard and loopback requests."""
    global _adapter
    with _adapter_lock:
        if _adapter is None or _adapter.runtime is not runtime:
            _adapter = RuntimeAdapter(runtime, audit or logging.getLogger(__name__))
        elif audit is not None:
            _adapter.audit = audit
        return _adapter


def estimate(values):
    """Count known retained objects once; shared array storage remains approximate."""
    seen = set()
    totals = dict(frame_bytes=0, export_bytes=0)

    def visit(value):
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, pd.DataFrame):
            totals['frame_bytes'] += int(value.memory_usage(deep=True).sum())
        elif isinstance(value, (bytes, bytearray)):
            totals['export_bytes'] += len(value)
        elif isinstance(value, dict):
            for item in list(value.values()):
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
        elif hasattr(value, 'frame') and isinstance(value.frame, pd.DataFrame):
            visit(value.frame)
    visit(values)
    return totals


class RuntimeAdapter:
    def __init__(self, runtime, audit):
        self.runtime, self.audit = runtime, audit
        self.manager = runtime._session_mgr
        self.loop = runtime._get_async_objs().eventloop
        if not all(hasattr(self.manager, name) for name in ('list_sessions', 'list_active_sessions', 'get_session_info')):
            raise RuntimeError('Unsupported Streamlit session manager; administration unavailable.')
        uploads = runtime.uploaded_file_mgr
        if not all(hasattr(uploads, name) for name in ('_lock', 'file_storage')):
            raise RuntimeError('Unsupported Streamlit upload manager; administration unavailable.')
        self.records = {}
        self.fingerprints = {}
        self.pending = {}
        self.activities = {}
        self.activity_tokens = {}
        self.idle_policy = dict(enabled=False, minutes=DEFAULT_IDLE_MINUTES)
        self.last_automatic_termination = None
        self.process = psutil.Process()
        self.process.cpu_percent()

    def call(self, method, *args):
        future = concurrent.futures.Future()
        def invoke():
            if future.cancelled():
                return
            try:
                future.set_result(getattr(self, method)(*args))
            except Exception as error:
                future.set_exception(error)
        self.loop.call_soon_threadsafe(invoke)
        return future.result(timeout=15)

    def register_activity(self, sid):
        info = self.manager.get_session_info(sid)
        if info is None or sid in self.pending:
            return None
        tracked = self.activities.get(sid)
        if tracked is None:
            tracked = self.activities[sid] = BrowserActivity(secrets.token_urlsafe(32), time.time())
            self.activity_tokens[tracked.token] = sid
        runner = info.session._scriptrunner
        if runner is not None:
            # Blinker deduplicates the bound receiver on successive reruns of one runner.
            runner.on_event.connect(self._script_event)
        return tracked.token

    def _script_event(self, runner, event, **_):
        from streamlit.runtime.scriptrunner import ScriptRunnerEvent

        if event in (ScriptRunnerEvent.SCRIPT_STOPPED_WITH_SUCCESS,
                     ScriptRunnerEvent.SCRIPT_STOPPED_WITH_COMPILE_ERROR,
                     ScriptRunnerEvent.FRAGMENT_STOPPED_WITH_SUCCESS):
            self.loop.call_soon_threadsafe(self._mark_activity, runner._session_id, time.time())

    def _mark_activity(self, sid, at):
        tracked = self.activities.get(sid)
        if tracked is not None:
            tracked.last_activity = max(tracked.last_activity, at)

    def report_activity(self, token):
        sid = self.activity_tokens.get(token)
        if sid is None or sid in self.pending or self.manager.get_active_session_info(sid) is None:
            return False
        self._mark_activity(sid, time.time())
        return True

    def _forget_activity(self, sid):
        tracked = self.activities.pop(sid, None)
        if tracked is not None:
            self.activity_tokens.pop(tracked.token, None)

    def _idle_status(self, session, page_activity, now):
        tracked = self.activities.get(session.id)
        latest = max(page_activity or 0, tracked.last_activity if tracked else 0)
        # The runtime holds the runner until it processes its shutdown event.
        busy = session._scriptrunner is not None
        return latest or None, None if busy or not latest else max(0, now - latest), busy

    def snapshot(self):
        now = time.time()
        active = {item.session.id: item for item in self.manager.list_active_sessions()}
        present = set()
        for info in self.manager.list_sessions():
            session = info.session
            sid = session.id
            # Never retain the state or frames in the monitoring registry.
            values = session.session_state.filtered_state
            if not values.get('_admin_page') and not values.get('_admin_activity'):
                # Streamlit can retain an internal/initializing connection with no app execution.
                # It owns no dashboard state and otherwise reappears as a phantom “— / —” row.
                self.records.pop(sid, None)
                self.fingerprints.pop(sid, None)
                continue
            present.add(sid)
            record = self.records.setdefault(sid, dict(id=sid, created_at=now, last_activity=None))
            dataset = values.get('dataset')
            # Deep string-column accounting can be expensive: reuse it while retained
            # objects and page activity are unchanged, without keeping object references.
            fingerprint = (values.get('_admin_activity'), tuple((key, id(value)) for key, value in values.items()))
            if self.fingerprints.get(sid) != fingerprint:
                record.update(estimate(values))
                self.fingerprints[sid] = fingerprint
            latest, idle, busy = self._idle_status(session, values.get('_admin_activity'), now)
            record.update(dataset=getattr(dataset, 'name', None), rows=len(dataset.frame) if dataset is not None else 0,
                          columns=len(dataset.frame.columns) if dataset is not None else 0,
                          page=values.get('_admin_page'), last_activity=latest, idle_seconds=idle, busy=busy)
            private_id = values.get('session_id')
            if private_id:
                uuid.UUID(private_id)
                record['private_id'] = private_id
            client = getattr(active.get(sid), 'client', None)
            context = getattr(client, 'client_context', None)
            address = getattr(context, 'remote_ip', None)
            if address:
                record['address'] = address
            try:
                local = ipaddress.ip_address(record.get('address', '')).is_loopback
                record['location'] = 'local' if local else 'remote'
            except ValueError:
                record['location'] = 'unknown'
            record['state'] = 'terminating' if sid in self.pending else ('connected' if sid in active else 'disconnected')
            manager = self.runtime.uploaded_file_mgr
            with manager._lock:
                record['upload_bytes'] = sum(len(f.data) for f in manager.file_storage.get(sid, {}).values())
            directory = ROOT / record['private_id'] if record.get('private_id') else None
            record['disk_bytes'] = sum(p.stat().st_size for p in directory.glob('*') if p.is_file()) if directory and directory.exists() else 0
        self.reap()
        for sid in self.activities.keys() - present:
            if self.manager.get_session_info(sid) is None:
                self._forget_activity(sid)
        # Expired disconnected sessions no longer own files; retry locked files later.
        for sid in list(self.records):
            if sid not in present and sid not in self.pending:
                if self.remove_files(self.records[sid]):
                    del self.records[sid]
                    self.fingerprints.pop(sid, None)
        return dict(sessions=list(self.records.values()), process_rss_bytes=self.process.memory_info().rss,
                    process_cpu_percent=self.process.cpu_percent(), available_ram_bytes=psutil.virtual_memory().available,
                    sampled_at=now, idle_policy=self.idle_policy,
                    last_automatic_termination=self.last_automatic_termination)

    @staticmethod
    def remove_files(record):
        if not record.get('private_id'):
            return True
        uuid.UUID(record['private_id'])
        try:
            shutil.rmtree(ROOT / record['private_id'])
        except FileNotFoundError:
            pass
        except OSError:
            return False
        return True

    def set_idle_policy(self, enabled, minutes):
        if type(enabled) is not bool or type(minutes) is not int or minutes not in IDLE_MINUTES:
            raise ValueError('Invalid idle policy.')
        policy = dict(enabled=enabled, minutes=minutes)
        if policy != self.idle_policy:
            self.idle_policy = policy
            self.audit.info('automatic idle policy enabled=%s threshold_minutes=%s', enabled, minutes)
        return self.idle_policy

    def monitor(self):
        # Reuse the periodic snapshot for cleanup and eligibility discovery.
        records = self.snapshot()['sessions']
        if not self.idle_policy['enabled']:
            return
        minutes = self.idle_policy['minutes']
        counts = self._terminate_idle_records(minutes, records)
        if counts['terminated'] or counts['terminating'] or counts['failed']:
            self.last_automatic_termination = dict(minutes=minutes, at=time.time(), **counts)
            self.audit.info('automatic idle termination threshold_minutes=%s outcomes=%s', minutes, counts)

    def terminate_idle(self, minutes):
        if type(minutes) is not int or minutes not in IDLE_MINUTES:
            raise ValueError('Invalid idle threshold.')
        counts = self._terminate_idle_records(minutes, self.snapshot()['sessions'])
        self.audit.info('idle termination threshold_minutes=%s outcomes=%s', minutes, counts)
        return counts

    def _terminate_idle_records(self, minutes, records):
        counts = dict(terminated=0, terminating=0, skipped=0, failed=0)
        for record in records:
            sid = record['id']
            try:
                info = self.manager.get_session_info(sid)
                if info is None or sid in self.pending:
                    counts['skipped'] += 1
                    continue
                state = info.session.session_state
                page_activity = state['_admin_activity'] if '_admin_activity' in state else None
                _, idle, _ = self._idle_status(info.session, page_activity, time.time())
                if idle is None or idle <= minutes * 60:
                    counts['skipped'] += 1
                    continue
                state = self.terminate(sid, inspected=True)['state']
                counts[state] += 1
            except KeyError:
                counts['skipped'] += 1
            except Exception:
                counts['failed'] += 1
                self.audit.exception('idle termination failed session=%s', sid)
        return counts

    def terminate(self, sid, private_id=None, *, inspected=False):
        if sid in self.pending:
            return dict(id=sid, state='terminating')
        info = self.manager.get_session_info(sid)
        if info is None:
            raise KeyError(sid)
        client = getattr(info, 'client', None)
        if client is not None and not (hasattr(client, 'close') or hasattr(client, '_websocket')):
            raise RuntimeError('Unsupported Streamlit client transport; termination unavailable.')
        if private_id is None:
            if not inspected:
                self.snapshot()
            if sid not in self.records:
                raise KeyError(sid)
        else:
            # A just-claimed upload may be stopped before its first projection.
            self.records.setdefault(sid, dict(id=sid))['private_id'] = private_id
        session = info.session
        # The flag prevents an ingestion result from being committed after cancellation.
        session.session_state['_admin_terminating'] = True
        runner = session._scriptrunner
        thread = getattr(runner, '_script_thread', None)
        self.pending[sid] = (session, thread)
        self.records[sid]['state'] = 'terminating'
        self.audit.info('terminate requested session=%s', sid)
        # Closing a session alone does not close the browser's WebSocket.
        self.runtime.close_session(sid)
        self._forget_activity(sid)
        reason = 'Session ended by client' if private_id else 'Session ended by administrator'
        if client is not None and hasattr(client, 'close'):
            client.close(code=1000, reason=reason)
        elif client is not None and hasattr(client, '_websocket'):
            # Streamlit 1.60 uses an ASGI client; its transport close is asynchronous.
            self.loop.create_task(client._websocket.close(code=1000, reason=reason))
        self.reap()
        return dict(id=sid, state='terminating' if sid in self.pending else 'terminated')

    def reap(self):
        for sid, (session, thread) in list(self.pending.items()):
            if thread is not None and thread.is_alive():
                continue
            session.session_state.clear()
            if self.remove_files(self.records[sid]):
                self.pending.pop(sid)
                self.records.pop(sid, None)
                self.fingerprints.pop(sid, None)
                self.audit.info('terminate completed session=%s', sid)


def activity(page):
    """Small shared-page hook; normal launches do not create administration state."""
    import os
    check_cancelled()
    if os.environ.get('DASHBOARD_ADMIN') != '1':
        return
    import streamlit as st
    st.session_state['_admin_activity'] = time.time()
    st.session_state['_admin_page'] = Path(page).stem
    from framework.admin_activity import mount_reporter
    mount_reporter()


def check_cancelled():
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    ctx = get_script_run_ctx(suppress_warning=True)
    # Clear may wipe widget state while termination is queued. The runtime
    # retains the cancellation independently until the script thread exits.
    if ctx and ((_adapter is not None and ctx.session_id in _adapter.pending)
                or st.session_state.get('_admin_terminating')):
        st.stop()
