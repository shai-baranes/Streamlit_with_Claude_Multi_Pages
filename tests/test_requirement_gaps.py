"""Regression coverage for session lifecycle and documented engineering contracts."""
import io
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from framework import data
from framework.analysis import transition_mask
from framework.session import stage_source, commit_projection
from framework.trajectory import prepare_trajectory


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'private')
    return {'session_id': str(uuid.uuid4())}


def stage(state, text='a,b,c\n1,2,3\n', name='same.csv'):
    return stage_source(state, io.BytesIO(text.encode()), name)


def test_projection_order_and_metadata(session):
    path = stage(session)
    for parquet in (False, True, True):
        result = data.load_dataset(path, 'same.csv', ['c', 'missing', 'a', 'c'], parquet)
        assert result.selected == ['c', 'a']
        assert list(result.frame) == ['c', 'a']
        assert result.frame.iloc[0].tolist() == [3, 1]


def test_atomic_lifecycle_deletes_only_obsolete_private_files(session, tmp_path):
    first = stage(session)
    commit_projection(session, ['a'], True)
    first_cache = next(first.parent.glob('*.parquet'))
    session['export:test'] = {'bytes': b'old'}
    session['value:test:field'] = 'a'
    pending = stage(session, 'other\n2\n')
    with pytest.raises(ValueError, match='Select at least'):
        commit_projection(session, ['a'])
    assert session['dataset'].source == first
    assert first.exists() and first_cache.exists()
    assert session['export:test']['bytes'] == b'old'
    newer = stage(session)
    assert not pending.exists()
    with pytest.raises(ValueError):
        stage(session, 'a,a\n1,2\n')
    assert session['pending_source'] == newer
    commit_projection(session, ['b'])
    assert not first.exists() and not first_cache.exists()
    assert newer.exists() and 'pending_source' not in session
    assert 'export:test' not in session and 'value:test:field' not in session

    # Directly seeded external sources (including CLI originals) are never deleted.
    original = tmp_path / 'original.csv'
    original.write_text('a\n9\n')
    session['dataset'] = data.load_dataset(original, original.name, ['a'])
    stage(session)
    commit_projection(session, ['a'])
    assert original.read_text() == 'a\n9\n'


def test_sessions_with_identical_names_stay_independent(session):
    other = {'session_id': str(uuid.uuid4())}
    one = stage(session)
    two = stage(other, 'a\n9\n')
    commit_projection(session, ['a'], True)
    commit_projection(other, ['a'], True)
    stage(session)
    commit_projection(session, ['c'])
    assert not one.exists() and two.exists()
    assert other['df_full'].a.tolist() == [9]


def test_cleanup_waits_for_staging(session, monkeypatch):
    entered, release, cleaned = threading.Event(), threading.Event(), threading.Event()
    inspect = data.inspect_header
    errors = []
    def blocked(path):
        entered.set()
        assert release.wait(3)
        return inspect(path)
    monkeypatch.setattr(data, 'inspect_header', blocked)
    def upload():
        try:
            stage(session)
        except Exception as error:
            errors.append(error)
    worker = threading.Thread(target=upload)
    worker.start()
    assert entered.wait(3)
    sweeper = threading.Thread(target=lambda: (data.cleanup(), cleaned.set()))
    sweeper.start()
    try:
        assert not cleaned.wait(.05)
    finally:
        release.set()
        worker.join(3)
        sweeper.join(3)
    assert not errors and cleaned.is_set()
    assert session['pending_source'].exists()


def test_cleanup_ignores_unrelated_directories(session):
    directory = data.ROOT / 'operator-files'
    directory.mkdir(parents=True)
    data.cleanup(now=directory.stat().st_mtime + data.TTL_SECONDS + 10)
    assert directory.exists()


@pytest.mark.parametrize('cached', [False, True])
def test_both_paths_enforce_frame_limit(session, monkeypatch, cached):
    path = stage(session)
    data.load_projection(path, ['a'], True)
    monkeypatch.setattr(data, 'MAX_FRAME_MB', 0)
    with pytest.raises(ValueError, match='fewer columns'):
        data.load_projection(path, ['a'], cached)


@pytest.mark.parametrize('cached', [False, True])
def test_both_paths_enforce_process_limit_after_admission(session, monkeypatch, cached):
    path = stage(session)
    data.load_projection(path, ['a'], True)
    monkeypatch.setattr(data, 'MAX_FRAME_MB', 1)
    monkeypatch.setattr(data, 'MAX_PROCESS_MB', 10)
    calls = iter([0, 11 * 1024**2])
    monkeypatch.setattr(data.psutil, 'Process', lambda: SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=next(calls))))
    with pytest.raises(ValueError, match='memory budget reached'):
        data.load_projection(path, ['a'], cached)


@pytest.mark.parametrize('dtype', ['float64', 'Float64', 'string'])
def test_null_transitions_preserve_first_and_actual_changes(dtype):
    values = [None, None, 1, 1, None, None, 2]
    if dtype == 'string':
        values = [None if v is None else str(v) for v in values]
    frame = pd.DataFrame({'anchor': pd.Series(values, dtype=dtype), 'other': [0,0,0,1,1,1,1]})
    assert frame.index[transition_mask(frame, ['anchor'])].tolist() == [0,2,4,6]
    assert frame.index[transition_mask(frame, ['anchor', 'other'])].tolist() == [0,2,3,4,6]


def test_trajectory_rejects_all_nonfinite_fields():
    frame = pd.DataFrame({'Seconds': [0., 1., 2., 3., 4.],
                          'longitude': [10.] * 5, 'latitude': [20.] * 5, 'Altitude': [30.] * 5})
    for row, column in enumerate(frame.columns, start=1):
        frame.loc[row, column] = np.inf if row % 2 else -np.inf
    result = prepare_trajectory(frame)
    assert result.invalid_rows == 4 and len(result.frame) == 1


def test_export_survives_reruns_and_invalidates_without_serializing(monkeypatch):
    calls = []
    original = pd.DataFrame.to_csv
    def tracked(frame, *args, **kwargs):
        calls.append(len(frame))
        return original(frame, *args, **kwargs)
    monkeypatch.setattr(pd.DataFrame, 'to_csv', tracked)
    script = '''
import pandas as pd
import streamlit as st
from framework.exports import render_csv_export
st.session_state.setdefault('df_full', pd.DataFrame({'a':[1,2,3], 'b':[4,5,6]}))
limit = st.slider('Rows', 1, 3, 3)
columns = st.multiselect('Columns', ['a','b'], default=['a'])
st.checkbox('Unrelated')
render_csv_export(st.session_state.df_full.iloc[:limit][columns], page='test.py', context=limit)
'''
    app = AppTest.from_string(script).run()
    assert not calls
    app.button[0].click().run()
    assert calls == [3] and len(app.get('download_button')) == 1
    app.checkbox[0].check().run()
    assert calls == [3] and len(app.get('download_button')) == 1
    app.slider[0].set_value(2).run()
    assert calls == [3] and len(app.get('download_button')) == 0
    app.button[0].click().run()
    app.multiselect[0].set_value(['b', 'a']).run()
    assert calls == [3,2] and len(app.get('download_button')) == 0
    other = AppTest.from_string(script).run()
    assert not other.get('download_button') and not app.exception
