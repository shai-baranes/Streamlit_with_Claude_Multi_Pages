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
                 get_session_info=lambda sid: sessions.get(sid),
                 get_active_session_info=lambda sid: sessions.get(sid) if sid in active else None)
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
    from streamlit.runtime import scriptrunner
    monkeypatch.delenv('DASHBOARD_ADMIN', raising=False)
    monkeypatch.setattr(scriptrunner, 'get_script_run_ctx', lambda **kwargs: NS(session_id='test'))
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
    html = (assets / 'admin.html').read_text(encoding='utf-8')
    script = (assets / 'admin.js').read_text(encoding='utf-8')
    styles = (assets / 'admin.css').read_text(encoding='utf-8')
    assert 'Administration token' not in html and 'id="connection-state"' in html
    assert 'Authorization' not in script and 'window.location.origin' in script
    assert '.connection.connected' in styles and '.connection.disconnected' in styles


def test_launcher_admin_opt_in(monkeypatch, capsys):
    import run_server
    import sys
    calls = []
    monkeypatch.setattr(run_server.subprocess,'call',lambda command, **kw: calls.append((command,kw)) or 0)
    monkeypatch.setattr(sys,'argv',['run_server.py','--admin','--admin-port','8532'])
    run_server.main()
    assert calls[0][0][2] == 'framework.admin_bootstrap'
    assert calls[0][1]['env']['DASHBOARD_ADMIN'] == '1'
    assert 'Server URL: http://127.0.0.1:8532' in capsys.readouterr().out


def test_owned_disconnected_session_can_stop_without_admin_activity(adapter):
    runtime, add = adapter
    sid, session, directory = add(connected=False, initialized=False)
    session.session_state['df_full'] = pd.DataFrame({'Seconds': [1, 2]})
    other_sid, other, other_dir = add()

    assert runtime.terminate(sid, directory.name)['state'] == 'terminated'
    assert not directory.exists() and not session.session_state
    assert runtime.manager.get_session_info(other_sid) is not None
    assert other_dir.exists() and 'df_full' in other.session_state


@pytest.mark.parametrize('minutes', ar.IDLE_MINUTES)
@pytest.mark.parametrize('automatic', [False, True])
def test_idle_termination_respects_cutoff_and_busy_work(adapter, monkeypatch, minutes, automatic):
    from streamlit.runtime.scriptrunner import ScriptRunnerEvent
    from streamlit.runtime.state.session_state import SessionState

    runtime, add = adapter
    now = 10000
    cutoff = now - minutes * 60
    monkeypatch.setattr(ar.time, 'time', lambda: now)
    old, disconnected, old_dir = add(connected=False)
    # Streamlit's internal state supports indexed access but has no dict.get().
    original = disconnected.session_state
    disconnected.session_state = SessionState()
    for key, value in original.items():
        disconnected.session_state[key] = value
    _, boundary, _ = add()
    _, busy, _ = add()
    _, unknown, _ = add()
    recent_sid, recent, _ = add()
    completed_sid, completed, _ = add()
    for session in (disconnected, busy, recent, completed):
        session.session_state['_admin_activity'] = cutoff - 1
    boundary.session_state['_admin_activity'] = cutoff
    unknown.session_state.pop('_admin_activity')
    busy._scriptrunner = object()

    # Browser input/playback and script completion both extend the idle window.
    token = runtime.register_activity(recent_sid)
    runtime.activities[recent_sid].last_activity = cutoff - 1
    assert runtime.report_activity(token)
    runtime.register_activity(completed_sid)
    runtime.activities[completed_sid].last_activity = cutoff - 1
    runtime._script_event(NS(_session_id=completed_sid), ScriptRunnerEvent.SCRIPT_STOPPED_WITH_SUCCESS)
    runtime.loop.run_until_complete(asyncio.sleep(0))

    expected = dict(terminated=1, terminating=0, skipped=5, failed=0)
    if automatic:
        runtime.set_idle_policy(True, minutes)
        runtime.monitor()
        outcome = dict(minutes=minutes, at=now, **expected)
        assert runtime.snapshot()['last_automatic_termination'] == outcome
        runtime.monitor()
        assert runtime.snapshot()['last_automatic_termination'] == outcome
    else:
        assert runtime.terminate_idle(minutes) == expected
    assert runtime.manager.get_session_info(old) is None and not old_dir.exists()
    assert runtime.terminate_idle(minutes)['terminated'] == 0


@pytest.mark.parametrize('automatic', [False, True])
def test_idle_batch_rechecks_sessions_and_continues_after_errors(adapter, monkeypatch, automatic):
    runtime, add = adapter
    failed, _, _ = add()
    first, _, _ = add()
    active, session, _ = add()
    last, _, _ = add()
    monkeypatch.setattr(ar.time, 'time', lambda: 10000)
    original = runtime.terminate

    def terminate(sid, **kwargs):
        if sid == failed:
            raise RuntimeError('Unavailable transport')
        if sid == first:
            session.session_state['_admin_activity'] = 10000
        return original(sid, **kwargs)

    monkeypatch.setattr(runtime, 'terminate', terminate)
    expected = dict(terminated=2, terminating=0, skipped=1, failed=1)
    if automatic:
        runtime.set_idle_policy(True, 5)
        runtime.monitor()
        assert runtime.last_automatic_termination == dict(minutes=5, at=10000, **expected)
    else:
        assert runtime.terminate_idle(5) == expected
    assert runtime.manager.get_session_info(last) is None
    assert runtime.manager.get_session_info(active) is not None


def test_monitor_uses_current_policy(adapter, monkeypatch):
    runtime, add = adapter
    sid, _, _ = add()
    monkeypatch.setattr(ar.time, 'time', lambda: 500)
    assert runtime.snapshot()['idle_policy'] == {'enabled': False, 'minutes': 15}
    runtime.set_idle_policy(False, 5)
    runtime.monitor()
    runtime.set_idle_policy(True, 15)
    runtime.monitor()
    assert runtime.manager.get_session_info(sid) is not None
    runtime.set_idle_policy(True, 5)
    runtime.set_idle_policy(False, 5)
    runtime.monitor()
    assert runtime.manager.get_session_info(sid) is not None
    runtime.set_idle_policy(True, 5)
    runtime.monitor()
    assert runtime.manager.get_session_info(sid) is None


def test_idle_policy_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(transport, 'admin_state_directory', lambda _: tmp_path / 'private')
    server = transport.AdminServer(0)
    calls = []

    def call(method, enabled, minutes):
        calls.append((method, enabled, minutes))
        if not enabled:
            raise RuntimeError('Unavailable')
        return dict(enabled=enabled, minutes=minutes)

    server.adapter = NS(call=call)
    url = f'http://127.0.0.1:{server.http.server_port}/idle-policy'

    def post(body, **headers):
        return urlopen(Request(url, json.dumps(body).encode(), headers), timeout=5)

    try:
        valid = {'enabled': True, 'minutes': 30}
        for body, headers, status in [
            ({'minutes': 5}, {}, 400),
            ({'enabled': 'true', 'minutes': 5}, {}, 400),
            ({'enabled': True, 'minutes': 10}, {}, 400),
            ({'enabled': True, 'minutes': True}, {}, 400),
            (valid, {'Origin': 'http://evil.test'}, 403),
            (valid, {'Host': 'evil.test'}, 403),
            ({'enabled': False, 'minutes': 30}, {}, 503),
        ]:
            with pytest.raises(HTTPError) as error:
                post(body, **headers)
            assert error.value.code == status
        with post(valid) as response:
            assert json.load(response) == valid
        assert calls == [('set_idle_policy', False, 30), ('set_idle_policy', True, 30)]
    finally:
        server.close()


def test_activity_credentials_are_isolated_and_removed(adapter, monkeypatch):
    runtime, add = adapter
    first, _, _ = add()
    second, _, _ = add()
    monkeypatch.setattr(ar.time, 'time', lambda: 100)
    a = runtime.register_activity(first)
    b = runtime.register_activity(second)
    assert a != b and runtime.register_activity(first) == a
    monkeypatch.setattr(ar.time, 'time', lambda: 200)
    assert not runtime.report_activity('invalid')
    assert runtime.report_activity(a)
    assert runtime.activities[first].last_activity == 200
    assert runtime.activities[second].last_activity == 100
    runtime.terminate(first)
    assert a not in runtime.activity_tokens and not runtime.report_activity(a)
    runtime.runtime.close_session(second)
    runtime.snapshot()
    assert b not in runtime.activity_tokens


def test_idle_transport_validates_threshold_and_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(transport, 'admin_state_directory', lambda _: tmp_path / 'private')
    server = transport.AdminServer(0)
    calls = []
    counts = dict(terminated=1, terminating=1, skipped=2, failed=0)
    server.adapter = NS(call=lambda *args: calls.append(args) or counts)
    url = f'http://127.0.0.1:{server.http.server_port}/terminate-idle'

    def post(value, **headers):
        return urlopen(Request(url, json.dumps(value).encode(), headers), timeout=5)

    try:
        for body in ({'minutes': '5'}, {'minutes': True}, {'minutes': 10}, {}, [5]):
            with pytest.raises(HTTPError) as error:
                post(body)
            assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            post({'minutes': 5}, Origin='http://evil.test')
        assert error.value.code == 403
        with post({'minutes': 15}) as response:
            assert response.status == 202 and json.load(response) == counts
        assert calls == [('terminate_idle', 15)]
    finally:
        server.close()


def test_activity_route_rejects_invalid_credentials_and_origins(adapter, monkeypatch):
    from starlette.requests import Request
    from framework import admin_activity

    runtime, add = adapter
    sid, _, _ = add()
    token = runtime.register_activity(sid)
    monkeypatch.setattr(ar, 'shared_adapter', lambda _: runtime)
    import streamlit.runtime
    monkeypatch.setattr(streamlit.runtime, 'get_instance', lambda: runtime.runtime)

    def post(**headers):
        request = Request({'type': 'http', 'scheme': 'http', 'path': '/api/session-activity',
                           'server': ('localhost', 8501),
                           'headers': [(name.encode(), value.encode()) for name, value in headers.items()]})
        return asyncio.run(admin_activity.report(request)).status_code

    monkeypatch.setenv('DASHBOARD_ADMIN', '0')
    assert post() == 404
    monkeypatch.setenv('DASHBOARD_ADMIN', '1')
    assert post() == 400
    assert post(**{'x-dashboard-activity': 'a' * 43}) == 403
    assert post(**{'x-dashboard-activity': token, 'origin': 'http://evil.test'}) == 403
    assert post(**{'x-dashboard-activity': token, 'origin': 'http://localhost:8501'}) == 204


def test_activity_reporter_mounts_once_per_run_and_survives_clear(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from framework import admin_activity

    calls = []
    monkeypatch.setenv('DASHBOARD_ADMIN', '1')
    monkeypatch.setattr(ar, 'shared_adapter', lambda _: NS(
        call=lambda method, sid: calls.append((method, sid)) or 'a' * 43))
    app = AppTest.from_string("""
import streamlit as st
from framework.admin_runtime import activity
activity('loader')
activity('loader')
if st.button('Clear'):
    st.session_state.clear()
    st.rerun()
""")
    try:
        app.run()
        assert not app.exception and len(app.get('bidi_component')) == 1
        app.button[0].click().run()
        assert not app.exception and len(app.get('bidi_component')) == 1
        assert len(calls) == 3 and len({sid for _, sid in calls}) == 1
    finally:
        admin_activity._reporter.clear()
