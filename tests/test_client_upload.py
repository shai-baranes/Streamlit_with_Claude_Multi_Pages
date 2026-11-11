import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
import uuid

import pytest
from starlette.requests import Request
from streamlit.testing.v1 import AppTest

from framework import client_upload, data


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'sessions')
    directory = tmp_path / 'staged'
    directory.mkdir()
    result = client_upload.Staging(directory, 128)
    monkeypatch.setattr(client_upload, 'staging', result)
    return result


def post(body, *, size=None, disconnect=False, name='דוח flight.csv', owner=None):
    async def receive():
        if chunks:
            return {'type': 'http.request', 'body': chunks.pop(0),
                    'more_body': bool(chunks) or disconnect}
        return {'type': 'http.disconnect'}

    chunks = [body[:4], body[4:]]
    request = Request({
        'type': 'http', 'method': 'POST',
        'query_string': urlencode({'filename': name, 'parquet': 'true'}).encode(),
        'headers': [(b'content-length', str(len(body) if size is None else size).encode())],
    }, receive)
    if owner is not None:
        request.scope['headers'].append((client_upload.OWNER_HEADER.encode(), owner.encode()))
    return asyncio.run(client_upload.upload_csv(request))


def token(response):
    assert response.status_code == 201
    return json.loads(response.body)['launch_url'].split('=')[1]


@pytest.mark.parametrize('body,size,disconnect,status', [
    (b'abc', 129, False, 413),
    (b'Seconds,Seconds\n1,2\n', None, False, 400),
    (b'Seconds\n1\n', 30, True, 408),
    (b'Seconds\n1\n', 30, False, 400),
])
def test_bad_upload_releases_capacity(store, body, size, disconnect, status):
    assert post(body, size=size, disconnect=disconnect).status_code == status
    assert store.bytes == 0
    assert store.receiving == 0
    assert not list(store.directory.iterdir())


def test_capacity_and_expiry(store, monkeypatch):
    assert store.reserve(128)
    assert store.reserve(128)
    assert post(b'Seconds\n1\n').status_code == 429
    store.finish(128)
    store.finish(128)
    clock = [0]
    monkeypatch.setattr(client_upload.time, 'monotonic', lambda: clock[0])
    link = token(post(b'Seconds\n1\n'))
    clock[0] = client_upload.TTL
    store.sweep()
    assert store.claim(link, str(uuid.uuid4())) is None
    assert store.bytes == 0
    assert not list(store.directory.iterdir())


def test_concurrent_claim_is_single_use(store):
    link = token(post(b'Seconds\n1\n'))
    with ThreadPoolExecutor(2) as workers:
        claimed = list(workers.map(lambda sid: store.claim(link, sid),
                                   [str(uuid.uuid4()), str(uuid.uuid4())]))
    [(path, name, parquet)] = [value for value in claimed if value]
    assert path.read_bytes() == b'Seconds\n1\n'
    assert name == 'דוח flight.csv' and parquet is True
    assert store.bytes == 0


def test_client_launch_beats_startup_and_does_not_replay(store, tmp_path, monkeypatch):
    startup = tmp_path / 'startup.csv'
    startup.write_text('Seconds\n99\n')
    monkeypatch.setattr(sys, 'argv', ['dashboard_server.py', '--csv_file', str(startup)])
    key = 'ab' * 32
    link = token(post(b'Seconds,Altitude,Extra\n1,15,x\n3,20,y\n', owner=key))
    entry = str(Path(__file__).resolve().parents[1] / 'Load CSV.py')
    app = AppTest.from_file(entry)
    app.query_params[client_upload.TOKEN_PARAM] = link
    app.run()
    assert not app.exception
    assert client_upload.TOKEN_PARAM not in app.query_params
    assert app.session_state['df_full'].Seconds.tolist() == [1, 3]
    assert app.slider[0].value == (1., 3.)
    assert app.checkbox[0].value is True
    ownership = dict(store.claimed)
    assert list(ownership.values()) == [(client_upload.owner_hash(key), app.session_state['session_id'])]
    version = app.session_state['dataset'].version
    app.switch_page('pages/0_🔧_Engineering_Explorer.py').run()
    app.switch_page('Load CSV.py').run()
    assert app.session_state['dataset'].version == version

    replay = AppTest.from_file(entry)
    replay.query_params[client_upload.TOKEN_PARAM] = link
    replay.run()
    assert 'dataset' not in replay.session_state
    assert 'already used' in replay.warning[0].value

    normal = AppTest.from_file(entry).run()
    assert normal.session_state['df_full'].Seconds.tolist() == [99]
    app.button[0].click().run()
    assert 'dataset' not in app.session_state
    assert store.claimed == ownership
    assert app.session_state['session_id'] == next(iter(ownership.values()))[1]


def test_failed_projection_keeps_claimed_file_for_manual_retry(store, monkeypatch):
    from framework import home

    link = token(post(b'Seconds,Altitude\n1,15\n3,20\n'))
    load = home.load_dataset
    calls = []

    def fail(*args):
        calls.append(args)
        raise ValueError('Memory limit reached')

    monkeypatch.setattr(home, 'load_dataset', fail)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'Load CSV.py'))
    app.query_params[client_upload.TOKEN_PARAM] = link
    app.run()
    assert app.error and 'dataset' not in app.session_state
    assert app.session_state['pending_source'].exists()
    app.run()
    assert len(calls) == 1

    monkeypatch.setattr(home, 'load_dataset', load)
    app.button[-1].click().run()
    assert app.session_state['df_full'].Seconds.tolist() == [1, 3]


def test_stop_revokes_only_matching_owner(store, monkeypatch):
    from types import SimpleNamespace

    key = 'ab' * 32
    digest = client_upload.owner_hash(key)
    other = client_upload.owner_hash('cd' * 32)
    sid = str(uuid.uuid4())
    private = str(uuid.uuid4())
    calls = []
    adapter = SimpleNamespace(
        terminate=lambda *args: calls.append(args) or {'state': 'terminating'},
        pending={sid: True}, reap=lambda: None,
    )
    monkeypatch.setattr(client_upload, 'controller', lambda: adapter)

    def stage(owner):
        assert store.reserve(1)
        path = store.directory / f'{uuid.uuid4()}.csv'
        path.write_bytes(b'x')
        return store.finish(1, client_upload.Upload(path, 'x.csv', False, 1, float('inf'), owner))

    def stop(headers):
        return asyncio.run(client_upload.stop_sessions(Request({'type': 'http', 'headers': headers})))

    assert store.claim(stage(digest), private, sid)
    doomed, unaffected = stage(digest), stage(other)
    assert stop([]).status_code == 400
    assert stop([(b'origin', b'https://example.org')]).status_code == 403
    header = client_upload.OWNER_HEADER.encode()
    assert json.loads(stop([(header, b'00' * 32)]).body) == dict(stopped=0, cancelled=0, terminating=0)
    counts = json.loads(stop([(header, key.encode())]).body)
    assert counts == dict(stopped=0, cancelled=1, terminating=1)
    assert calls == [(sid, private)]
    assert store.claim(doomed, str(uuid.uuid4()), 'doomed') is None
    assert store.claim(unaffected, str(uuid.uuid4()), 'unaffected')
    assert store.claim(stage(digest), str(uuid.uuid4()), 'new')
    assert store.bytes == 0


def test_stop_wakes_stalled_upload(store):
    async def exercise():
        waiting = asyncio.Event()

        async def receive():
            waiting.set()
            await asyncio.Future()

        key = 'ab' * 32
        request = Request({
            'type': 'http', 'method': 'POST',
            'query_string': b'filename=stalled.csv',
            'headers': [(b'content-length', b'20'), (client_upload.OWNER_HEADER.encode(), key.encode())],
        }, receive)
        task = asyncio.create_task(client_upload.upload_csv(request))
        await waiting.wait()
        assert store.cancel_group(client_upload.owner_hash(key)) == (1, {})
        assert (await asyncio.wait_for(task, timeout=2)).status_code == 409

    asyncio.run(exercise())
    assert store.receiving == store.bytes == 0
    assert not list(store.directory.iterdir())
