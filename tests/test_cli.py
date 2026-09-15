from pathlib import Path
import sys
import pytest
from streamlit.testing.v1 import AppTest
from framework import data
from framework.cli import startup_csv_options, validate_csv_path
import run_server

ROOT = Path(__file__).resolve().parents[1]


def test_launcher_preserves_default_and_forwards_path(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(run_server.subprocess, 'call', lambda command, **kwargs: commands.append(command) or 0)
    monkeypatch.setattr(sys, 'argv', ['run_server.py'])
    assert run_server.main() == 0
    assert '--' not in commands[-1]
    source = tmp_path / 'some data.CSV'
    source.write_text('time,value\n0,1\n')
    monkeypatch.setattr(sys, 'argv', ['run_server.py', '--debug', str(source)])
    assert run_server.main() == 0
    assert commands[-1][-2:] == ['--', str(source.resolve())]


def test_load_all_is_an_application_argument_only(tmp_path, monkeypatch):
    source = tmp_path / 'all.csv'
    source.write_text('a,b\n1,2\n')
    monkeypatch.setattr(sys, 'argv', ['Load CSV.py', str(source), '--load-all'])
    options = startup_csv_options()
    assert options.path == source.resolve() and options.load_all
    monkeypatch.setattr(sys, 'argv', ['Load CSV.py', '--load-all'])
    with pytest.raises(ValueError, match='requires a CSV path'):
        startup_csv_options()
    # The server wrapper must not interpret or expose this local application flag.
    monkeypatch.setattr(sys, 'argv', ['run_server.py', '--load-all'])
    with pytest.raises(SystemExit):
        run_server.main()


@pytest.mark.parametrize('entry', ['Load CSV.py'])
# @pytest.mark.parametrize('entry', ['Load CSV.py', 'Load CSV_2.py'])
def test_cli_stages_once_isolates_and_clears(tmp_path, monkeypatch, entry):
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'private')
    source = tmp_path / 'my data.csv'
    source.write_text('Date,extra\n01/01/2022,hello\n')
    monkeypatch.setattr(sys, 'argv', [str(ROOT / entry), str(source)])
    first = AppTest.from_file(str(ROOT / entry)).run()
    assert not first.exception
    assert any(source.name in item.value for item in first.text)
    staged = first.session_state['pending_source']
    assert staged != source and staged.read_bytes() == source.read_bytes()
    first.run()
    assert first.session_state['pending_source'] == staged
    second = AppTest.from_file(str(ROOT / entry)).run()
    assert second.session_state['pending_source'] != staged
    first.button[-1].click().run()
    assert list(first.session_state['df_full']) == ['Date']
    first.button[0].click().run()
    assert 'dataset' not in first.session_state
    assert 'pending_source' not in first.session_state
    assert source.exists()


def test_invalid_cli_keeps_upload_available(tmp_path, monkeypatch):
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'private')
    source = tmp_path / 'bad.csv'
    source.write_text('a,a\n1,2\n')
    monkeypatch.setattr(sys, 'argv', ['Load CSV.py', str(source)])
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    assert not app.exception
    assert any('Duplicate' in warning.value for warning in app.warning)
    assert 'pending_source' not in app.session_state


def test_sample_seconds_interval_is_applied_with_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'private')
    monkeypatch.setenv('DASHBOARD_SAMPLE', '1')
    monkeypatch.setattr(sys, 'argv', [str(ROOT / 'Load CSV.py')])
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    app.button[1].click().run()
    assert app.slider[0].label == 'Seconds interval'
    assert app.slider[0].value == (0.0, 749.5)
    app.slider[0].set_range(10.0, 20.0)
    app.button[-1].click().run()
    assert app.session_state['df_full'].Seconds.min() == 10.0
    assert app.session_state['df_full'].Seconds.max() == 20.0


def test_cli_load_all_bypasses_seconds_interval_and_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'private')
    source = tmp_path / 'startup.csv'
    source.write_text('Seconds,extra,value\n0,a,1\n1,b,2\n2,c,3\n')
    monkeypatch.setattr(sys, 'argv', [str(ROOT / 'Load CSV.py'), str(source), '--load-all'])
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    assert not app.exception
    assert list(app.session_state['df_full']) == ['Seconds', 'extra', 'value']
    assert app.session_state['df_full'].Seconds.tolist() == [0, 1, 2]
    assert not app.slider
    assert all(button.label != 'Apply columns' for button in app.button)


def test_rejects_missing_or_unsupported_path(tmp_path):
    with pytest.raises(ValueError, match='not found'):
        validate_csv_path(tmp_path / 'absent.csv')
    with pytest.raises(ValueError, match='extension'):
        validate_csv_path(tmp_path / 'file.txt')
