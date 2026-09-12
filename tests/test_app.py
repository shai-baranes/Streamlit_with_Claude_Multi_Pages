from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from framework.data import load_projection
from framework.config import ALWAYS_LOAD_COLUMNS

ROOT = Path(__file__).resolve().parents[1]

def test_home():
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    assert not app.exception
    assert 'Engineering Data Dashboard' in app.title[0].value
    assert app.get('file_uploader')[0].label == (
        'Drag and drop a CSV file here, or select it with Upload'
    )


def test_sample_action_is_optional(monkeypatch):
    monkeypatch.delenv('DASHBOARD_SAMPLE', raising=False)
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    assert all(button.label != 'Load sample data' for button in app.button)

    monkeypatch.setenv('DASHBOARD_SAMPLE', '1')
    app = AppTest.from_file(str(ROOT / 'Load CSV.py')).run()
    assert any(button.label == 'Load sample data' for button in app.button)

def test_widget_navigation_and_isolation():
    script = '''
import streamlit as real
from framework.state import ui
st = ui('example.py')
if real.session_state.get('visible', True):
    st.multiselect('Fields', ['a', 'b'], key='fields')
'''
    one = AppTest.from_string(script).run()
    two = AppTest.from_string(script).run()
    one.multiselect[0].set_value(['b']).run()
    one.session_state['visible'] = False
    one.run()
    one.session_state['visible'] = True
    one.run()
    assert not one.exception
    assert one.multiselect[0].value == ['b']
    assert two.multiselect[0].value == []

@pytest.mark.parametrize('page', [p for p in (ROOT / 'pages').glob('*.py') if 'Animated_Trajectory' not in p.name])
def test_pages_sample(page):
    compile(page.read_text(), str(page), "exec")
    app = AppTest.from_file(str(page))
    app.session_state['df_full'] = load_projection(ROOT / 'synthetic_sales_data.csv', ALWAYS_LOAD_COLUMNS)
    app.run(timeout=30)
    assert not app.exception

def test_engineering_and_sales_gate():
    import pandas as pd
    frame = pd.DataFrame({'time':[0,1,2], 'state':['a','a','b'], 'speed':[1,2,3]})
    for pattern in ['0_*', '1_*']:
        app = AppTest.from_file(str(next((ROOT / 'pages').glob(pattern))))
        app.session_state['df_full'] = frame
        app.run()
        assert not app.exception

def test_atomic_replacement_and_additional_columns(tmp_path):
    first = tmp_path / 'first.csv'
    first.write_text('time,state,speed\n0,on,2\n1,off,3\n')
    app = AppTest.from_file(str(ROOT / 'Load CSV.py'))
    app.session_state['pending_source'] = first
    app.session_state['pending_name'] = 'same.csv'
    app.run()
    app.multiselect[0].set_value(['time', 'state'])
    app.button[-1].click().run()
    assert list(app.session_state['df_full']) == ['time', 'state']
    app.multiselect[0].set_value(['time', 'state', 'speed'])
    app.button[-1].click().run()
    assert 'speed' in app.session_state['df_full']
    # A parse failure must leave the active dataset and its values intact.
    bad = tmp_path / 'bad.csv'
    bad.write_text('time\n"unclosed\n')
    app.session_state['pending_source'] = bad
    app.run()
    app.multiselect[0].set_value(['time'])
    app.button[-1].click().run()
    assert app.error
    assert app.session_state['df_full']['speed'].tolist() == [2, 3]


def test_scope_separates_legacy_callback_values():
    script = '''
import streamlit as st
from framework.state import ui
for name in ['first.py', 'second.py']:
    page = ui(name)
    page.multiselect(name, ['a','b'], key='selected_columns_ordered')
'''
    app = AppTest.from_string(script).run()
    app.multiselect[0].set_value(['b']).run()
    assert app.multiselect[1].value == []
    assert app.session_state['legacy:first:selected_columns_ordered'] == ['b']

def test_stacked_selection_and_initial_mode():
    page = next((ROOT / 'pages').glob('*Stacked_Values_Enhanced.py'))
    app = AppTest.from_file(str(page))
    app.session_state['df_full'] = load_projection(ROOT / 'synthetic_sales_data.csv', ALWAYS_LOAD_COLUMNS)
    app.run()
    assert next(w for w in app.selectbox if w.label == 'View mode').value == 'Stacked by Left'
    next(w for w in app.multiselect if w.label == 'Select columns to display').set_value(['Region']).run()
    assert not app.exception
    assert any('Region' in c.value and 'Anchor' in c.value for c in app.caption)
    next(w for w in app.selectbox if w.label == 'View mode').set_value('Full').run()
    assert not app.exception


def test_sales_filters_keep_full_range_across_reruns():
    script = '''
import streamlit as st
from utils import sidebar_filters
st.metric('Rows', len(sidebar_filters(st.session_state['df_full'])))
'''
    app = AppTest.from_string(script)
    frame = load_projection(ROOT / 'synthetic_sales_data.csv', ALWAYS_LOAD_COLUMNS)
    app.session_state['df_full'] = frame
    app.run().run()
    assert not app.exception
    assert int(app.metric[0].value) == len(frame)


def test_sales_filters_with_missing_categories_and_constant_revenue():
    script = '''
import streamlit as st
from utils import sidebar_filters
st.dataframe(sidebar_filters(st.session_state['df_full']))
'''
    app = AppTest.from_string(script)
    frame = load_projection(ROOT / 'synthetic_sales_data.csv', ALWAYS_LOAD_COLUMNS).head(3).copy()
    frame.loc[0, 'Region'] = None
    frame['Revenue'] = 10.0
    app.session_state['df_full'] = frame
    app.run()
    assert not app.exception


def test_header_only_dataset_has_explanation():
    import pandas as pd
    app = AppTest.from_file(str(next((ROOT / 'pages').glob('0_*'))))
    app.session_state['df_full'] = pd.DataFrame(columns=['time', 'speed'])
    app.run()
    assert not app.exception
    assert any('no data rows' in message.value for message in app.info)
