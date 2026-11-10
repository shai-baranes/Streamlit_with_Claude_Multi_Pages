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


@pytest.mark.parametrize('admin', [False, True])
@pytest.mark.parametrize('value', ['true', 'FALSE'])
def test_named_launcher_arguments(tmp_path, monkeypatch, admin, value):
    source = tmp_path / 'some data.csv'
    source.write_text('Seconds\n0\n')
    commands = []
    monkeypatch.setattr(run_server.subprocess, 'call', lambda command, **kwargs: commands.append(command) or 0)
    monkeypatch.setattr(sys, 'argv', ['run_server.py', '--csv_file', str(source), '--parquet', value] + (['--admin'] if admin else []))
    assert run_server.main() == 0
    command = commands[0]
    forwarded = command[command.index('--') + 1:]
    assert forwarded[:2] == ['--csv_file', str(source.resolve())]
    assert ('--parquet' in forwarded) == (value == 'true')
    assert command[2] == ('framework.admin_bootstrap' if admin else 'streamlit')


@pytest.mark.parametrize('args', [ ['--parquet', 'yes'], ['--parquet'], ['a.csv', '--csv_file', 'b.csv'] ])
def test_bad_launcher_options(monkeypatch, args):
    monkeypatch.setattr(sys, 'argv', ['run_server.py', *args])
    with pytest.raises(SystemExit):
        run_server.main()


def test_named_load_all_conflict(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['Load CSV.py', '--csv_file', 'a.csv', '--load-all'])
    with pytest.raises(ValueError, match='cannot be combined'):
        startup_csv_options()


@pytest.mark.parametrize('seconds,expected', [
    ('0\n1\n2\n', [0, 1, 2]),
    ('1\n1\n', [1, 1]),
    ('bad\n\"\"\n', ['bad', None]),
    ('0\nbad\n2\n', [0, 2]),
])
@pytest.mark.parametrize('parquet', [True, False])
def test_named_startup_applies_once(tmp_path, monkeypatch, seconds, expected, parquet):
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'private')
    source = tmp_path / 'startup.csv'
    source.write_text('Seconds,extra\n' + ''.join(line + ',x\n' for line in seconds.strip().splitlines()))
    monkeypatch.setattr(sys, 'argv', ['Load CSV.py', '--csv_file', str(source), '--parquet', str(parquet)])
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    assert not app.exception
    frame = app.session_state['df_full']
    assert list(frame.columns) == ['Seconds']
    assert len(frame) == len(expected)
    if expected[0] != 'bad':
        assert frame.Seconds.astype(float).tolist() == expected
    if app.slider:
        assert app.slider[0].value == (0.0, 2.0)
    assert any(b.label == 'Apply columns' for b in app.button)
    assert app.checkbox[0].value == parquet
    source_path = app.session_state['dataset'].source
    assert bool(list(source_path.parent.glob('*.parquet'))) == parquet
    version = app.session_state['dataset'].version
    app.run()
    assert app.session_state['dataset'].version == version
    other = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    assert other.session_state['dataset'].source != source_path
    app.checkbox[0].set_value(not parquet)
    app.button[-1].click().run()
    assert app.session_state['home:parquet'] == (not parquet)
    app.switch_page('pages/0_🔧_Engineering_Explorer.py').run()
    app.switch_page('Load CSV.py').run()
    assert app.checkbox[0].value == (not parquet)
    app.button[0].click().run()
    assert 'dataset' not in app.session_state
    assert source.exists()


@pytest.mark.parametrize('contents,loaded', [('Altitude,extra\n2,x\n', True), ('extra\nx\n', False), ('Seconds,Seconds\n0,1\n', False)])
def test_named_startup_missing_seconds_and_bad_schema(tmp_path, monkeypatch, contents, loaded):
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'private')
    source = tmp_path / 'source.csv'
    source.write_text(contents)
    monkeypatch.setattr(sys, 'argv', ['Load CSV.py', '--csv_file', str(source)])
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    assert not app.exception
    assert ('dataset' in app.session_state) == loaded
    if contents.startswith('extra'):
        assert any('No fixed fields' in item.value for item in app.info)


def test_parquet_default_without_startup(tmp_path, monkeypatch):
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'private')
    monkeypatch.setenv('DASHBOARD_SAMPLE', '1')
    monkeypatch.setattr(sys, 'argv', ['Load CSV.py', '--parquet', 'TRUE'])
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    app.button[1].click().run()
    assert app.checkbox[0].value is True
    assert 'dataset' not in app.session_state


def test_auto_apply_failure_is_not_retried(tmp_path, monkeypatch):
    from framework import home
    monkeypatch.setattr(data, 'ROOT', tmp_path / 'private')
    source = tmp_path / 'source.csv'
    source.write_text('Seconds\n0\n1\n')
    monkeypatch.setattr(sys, 'argv', ['Load CSV.py', '--csv_file', str(source)])
    calls = []
    original = home.load_dataset
    def fail(*args):
        calls.append(args)
        raise ValueError('Memory limit reached')
    monkeypatch.setattr(home, 'load_dataset', fail)
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    assert app.error and 'dataset' not in app.session_state
    app.run()
    assert len(calls) == 1
    monkeypatch.setattr(home, 'load_dataset', original)
    app.button[-1].click().run()
    assert len(app.session_state['df_full']) == 2
