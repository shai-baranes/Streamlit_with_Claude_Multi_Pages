"""Version-sensitive Streamlit administration, confined to its event loop."""
import concurrent.futures
import ipaddress
import shutil
import time
import uuid
from pathlib import Path

import pandas as pd
import psutil

from framework.config import ROOT


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

    def snapshot(self):
        now = time.time()
        active = {item.session.id: item for item in self.manager.list_active_sessions()}
        present = set()
        for info in self.manager.list_sessions():
            session = info.session
            sid = session.id
            present.add(sid)
            record = self.records.setdefault(sid, dict(id=sid, created_at=now, last_activity=None))
            # Never retain the state or frames in the monitoring registry.
            values = session.session_state.filtered_state
            dataset = values.get('dataset')
            # Deep string-column accounting can be expensive: reuse it while retained
            # objects and page activity are unchanged, without keeping object references.
            fingerprint = (values.get('_admin_activity'), tuple((key, id(value)) for key, value in values.items()))
            if self.fingerprints.get(sid) != fingerprint:
                record.update(estimate(values))
                self.fingerprints[sid] = fingerprint
            record.update(dataset=getattr(dataset, 'name', None), rows=len(dataset.frame) if dataset is not None else 0,
                          columns=len(dataset.frame.columns) if dataset is not None else 0,
                          page=values.get('_admin_page'), last_activity=values.get('_admin_activity', record['last_activity']))
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
            record['state'] = 'connected' if sid in active else 'disconnected'
            manager = self.runtime.uploaded_file_mgr
            with manager._lock:
                record['upload_bytes'] = sum(len(f.data) for f in manager.file_storage.get(sid, {}).values())
            directory = ROOT / record['private_id'] if record.get('private_id') else None
            record['disk_bytes'] = sum(p.stat().st_size for p in directory.glob('*') if p.is_file()) if directory and directory.exists() else 0
        self.reap()
        # Expired disconnected sessions no longer own files; retry locked files later.
        for sid in list(self.records):
            if sid not in present and sid not in self.pending:
                if self.remove_files(self.records[sid]):
                    del self.records[sid]
                    self.fingerprints.pop(sid, None)
        return dict(sessions=list(self.records.values()), process_rss_bytes=self.process.memory_info().rss,
                    process_cpu_percent=self.process.cpu_percent(), available_ram_bytes=psutil.virtual_memory().available,
                    sampled_at=now)

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

    def terminate(self, sid):
        if sid in self.pending:
            return dict(id=sid, state='terminating')
        info = self.manager.get_session_info(sid)
        if info is None:
            raise KeyError(sid)
        client = getattr(info, 'client', None)
        if client is not None and not (hasattr(client, 'close') or hasattr(client, '_websocket')):
            raise RuntimeError('Unsupported Streamlit client transport; termination unavailable.')
        self.snapshot()
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
        if client is not None and hasattr(client, 'close'):
            client.close(code=1000, reason='Session ended by administrator; refresh to start again')
        elif client is not None and hasattr(client, '_websocket'):
            # Streamlit 1.60 uses an ASGI client; its transport close is asynchronous.
            self.loop.create_task(client._websocket.close(code=1000, reason='Session ended by administrator'))
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
    if os.environ.get('DASHBOARD_ADMIN') != '1':
        return
    import streamlit as st
    if st.session_state.get('_admin_terminating'):
        st.stop()
    st.session_state['_admin_activity'] = time.time()
    st.session_state['_admin_page'] = Path(page).stem


def check_cancelled():
    import os
    if os.environ.get('DASHBOARD_ADMIN') == '1':
        import streamlit as st
        if st.session_state.get('_admin_terminating'):
            st.stop()
