"""Administration contracts without manipulating the user's running server."""
import asyncio
import json
import logging
from pathlib import Path
import threading
import uuid
from types import SimpleNamespace as NS
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pandas as pd
import pytest

import admin
from framework import admin_runtime as ar
from framework import admin_server as transport


class State(dict):
    @property
    def filtered_state(self):
        return dict(self)


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, 'ROOT', tmp_path)
    sessions = {}
    active = set()
    manager = NS(list_sessions=lambda: list(sessions.values()),
                 list_active_sessions=lambda: [sessions[s] for s in active],
                 get_session_info=lambda sid: sessions.get(sid))
    def close(sid):
        sessions.pop(sid, None)
        active.discard(sid)
    runtime = NS(_session_mgr=manager, _get_async_objs=lambda: NS(eventloop=asyncio.new_event_loop()),
                 close_session=close, uploaded_file_mgr=NS(_lock=threading.Lock(), file_storage={}))
    result = ar.RuntimeAdapter(runtime, logging.getLogger('test'))
    def add(connected=True, initialized=True):
        sid, private = str(uuid.uuid4()), str(uuid.uuid4())
        directory = tmp_path / private
        directory.mkdir()
        (directory / 'source.csv').write_text('a\n1\n')
        state = State()
        if initialized:
            state.update(
                session_id=private,
                df_full=pd.DataFrame({'a':[1,2]}),
                _admin_page='Load CSV',
                _admin_activity=1.0,
            )
        session = NS(id=sid, session_state=state, _scriptrunner=None)
        sessions[sid] = NS(session=session, client=NS(client_context=NS(remote_ip='127.0.0.1'), close=lambda **kw: None))
        if connected:
            active.add(sid)
        return sid, session, directory
    yield result, add
    result.loop.close()


def test_memory_aliases_and_nested_exports():
    frame = pd.DataFrame({'text':['abc', None]})
    payload = b'csv-data'
    result = ar.estimate({'dataset':NS(frame=frame), 'df_full':frame, 'cache':[payload,payload]})
    assert result == {'frame_bytes':int(frame.memory_usage(deep=True).sum()), 'export_bytes':8}


def test_discovery_and_termination_isolation(adapter):
    runtime, add = adapter
    first, session, directory = add()
    second, other, other_dir = add(False)
    snapshot = runtime.snapshot()['sessions']
    assert {s['state'] for s in snapshot} == {'connected','disconnected'}
    assert snapshot[0]['location'] == 'local'
    assert runtime.terminate(first)['state'] == 'terminated'
    assert not directory.exists() and not session.session_state
    assert other_dir.exists() and 'df_full' in other.session_state
    assert runtime.snapshot()['sessions'][0]['id'] == second
    with pytest.raises(KeyError):
        runtime.terminate(first)


def test_pending_native_work_and_cleanup_retry(adapter, monkeypatch):
    runtime, add = adapter
    sid, session, directory = add()
    alive = [True]
    session._scriptrunner = NS(_script_thread=NS(is_alive=lambda: alive[0]))
    assert runtime.terminate(sid)['state'] == 'terminating'
    assert session.session_state['_admin_terminating']
    assert runtime.terminate(sid)['state'] == 'terminating'
    assert directory.exists()
    alive[0] = False
    original = ar.shutil.rmtree
    monkeypatch.setattr(ar.shutil, 'rmtree', lambda _: (_ for _ in ()).throw(PermissionError()))
    runtime.reap()
    assert sid in runtime.pending
    monkeypatch.setattr(ar.shutil, 'rmtree', original)
    runtime.reap()
    assert sid not in runtime.pending and not directory.exists()


def test_expired_session_files_removed(adapter):
    runtime, add = adapter
    sid, _, directory = add(False)
    runtime.snapshot()
    runtime.runtime.close_session(sid)
    assert runtime.snapshot()['sessions'] == []
    assert not directory.exists()


def test_uninitialized_phantom_session_is_hidden_and_not_terminable(adapter):
    runtime, add = adapter
    sid, _, _ = add(initialized=False)
    assert runtime.snapshot()['sessions'] == []
    with pytest.raises(KeyError):
        runtime.terminate(sid)


def test_cancelled_ingestion_stops(monkeypatch):
    import streamlit as st
    from streamlit.runtime.scriptrunner_utils.exceptions import StopException
    monkeypatch.setenv('DASHBOARD_ADMIN','1')
    monkeypatch.setattr(st, 'session_state', {'_admin_terminating':True})
    monkeypatch.setattr(st, 'stop', lambda: (_ for _ in ()).throw(StopException()))
    with pytest.raises(StopException):
        ar.check_cancelled()


def test_transport_loopback_origin_and_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(transport, 'admin_state_directory', lambda _: tmp_path / 'private')
    server = transport.AdminServer(0)
    port = server.http.server_port
    server.adapter = NS(call=lambda method, *args: {'sessions':[]} if method == 'snapshot' else {'state':'terminating'})
    url = f'http://127.0.0.1:{port}'
    try:
        assert server.http.server_address[0] == '127.0.0.1'
        with urlopen(Request(url+'/sessions')) as response:
            assert json.load(response) == {'sessions': []}
        for headers, status in [({'Origin':'http://evil.test'},403), ({'Host':'localhost'},403)]:
            with pytest.raises(HTTPError) as error:
                urlopen(Request(url+'/sessions', headers=headers))
            assert error.value.code == status
        args = ['--port',str(port)]
        assert admin.main(args+['sessions','list','--json']) == 0
        assert 'sessions' in capsys.readouterr().out
        assert admin.main(args+['sessions','inspect','missing']) == 4
        assert admin.main(args+['sessions','terminate','test','--yes']) == 5
    finally:
        server.close()


def test_admin_console_has_tokenless_prominent_connection_states():
    assets = Path(transport.__file__).parent / 'admin_assets'
    html = (assets / 'admin.html').read_text()
    script = (assets / 'admin.js').read_text()
    styles = (assets / 'admin.css').read_text()
    assert 'Administration token' not in html and 'id="connection-state"' in html
    assert 'Authorization' not in script and 'window.location.origin' in script
    assert '.connection.connected' in styles and '.connection.disconnected' in styles


def test_launcher_admin_opt_in(monkeypatch):
    import run_server
    import sys
    calls = []
    monkeypatch.setattr(run_server.subprocess,'call',lambda command, **kw: calls.append((command,kw)) or 0)
    monkeypatch.setattr(sys,'argv',['run_server.py','--admin','--admin-port','8532'])
    run_server.main()
    assert calls[0][0][2] == 'framework.admin_bootstrap'
    assert calls[0][1]['env']['DASHBOARD_ADMIN'] == '1'
