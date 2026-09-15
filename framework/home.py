"""Shared upload page for both historical entry points."""
from pathlib import Path
import os
import shutil
import uuid
import streamlit as st
from framework.config import ALWAYS_LOAD_COLUMNS, MAX_UPLOAD_MB
from framework.data import (cleanup, save_source, inspect_header, inspect_numeric_range,
                            load_dataset, session_directory)
from framework.state import reset_controls
from framework.cli import startup_csv_argument


def render():
    # Register the home page as well as pages using the shared UI wrapper.
    from framework.admin_runtime import activity, check_cancelled
    activity('Load CSV')
    st.set_page_config(page_title='Engineering Data Dashboard', layout='wide')
    st.markdown(
        '''
        <style>
        /* Make the entire native Streamlit uploader an obvious file drop target. */
        [data-testid="stFileUploaderDropzone"] {
            min-height: 9rem;
            border: 2px dashed #3b82f6;
            border-radius: 0.85rem;
            background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
            padding: 1.5rem;
            transition: border-color 120ms ease, background-color 120ms ease;
        }
        [data-testid="stFileUploaderDropzone"]:hover {
            border-color: #1d4ed8;
            background: #dbeafe;
        }
        [data-testid="stFileUploaderDropzone"]::before {
            content: "⬇  DROP CSV FILE HERE";
            color: #1d4ed8;
            font-size: 1.05rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        [data-testid="stFileUploader"] > label p {
            font-size: 1rem;
            font-weight: 650;
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )
    st.title('Engineering Data Dashboard')
    cleanup()
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    session_directory(st.session_state.session_id)
    # Keep the optional sample action on the same row as the clear action.
    clear_col, _, sample_col = st.columns([1.2, 3, 1.4])
    clear_clicked = clear_col.button('Clear dataset', width='stretch')
    sample_clicked = False
    if os.environ.get('DASHBOARD_SAMPLE') == '1':
        sample_clicked = sample_col.button('Load sample data', width='stretch')

    if clear_clicked:
        shutil.rmtree(session_directory(st.session_state.session_id), ignore_errors=True)
        st.session_state.clear()
        # Clear must leave an empty session even when the server has a startup file.
        st.session_state['cli_initialized'] = True
        st.rerun()
    # Stage once, through the same validator/private storage used by browser uploads.
    if not st.session_state.get('cli_initialized'):
        st.session_state['cli_initialized'] = True
        if not st.session_state.get('dataset') and not st.session_state.get('pending_source'):
            try:
                cli_path = startup_csv_argument()
                if cli_path is not None:
                    with cli_path.open('rb') as source:
                        path = save_source(source, st.session_state.session_id)
                    st.session_state.update(pending_source=path, pending_name=cli_path.name)
            except Exception as error:
                st.session_state['cli_error'] = f'Startup CSV could not be loaded: {error}'
    if st.session_state.get('cli_error'):
        st.warning(st.session_state['cli_error'])
    # Streamlit's native drop zone accepts both an OS drag-and-drop and the
    # adjacent Upload button, and feeds both paths through the same validator.
    uploaded = st.file_uploader(
        'Drag and drop a CSV file here, or select it with Upload',
        type=['csv'],
        max_upload_size=MAX_UPLOAD_MB,
        help='Drag one .csv file from Finder or File Explorer onto this area, '
             'or click Upload to browse for it.',
    )
    if uploaded is not None and uploaded.file_id != st.session_state.get('upload_id'):
        try:
            path = save_source(uploaded, st.session_state.session_id)
            old_pending = st.session_state.get('pending_source')
            active = st.session_state.get('dataset')
            if old_pending and (active is None or old_pending != active.source):
                Path(old_pending).unlink(missing_ok=True)
            st.session_state.update(pending_source=path, pending_name=uploaded.name,
                                    upload_id=uploaded.file_id)
        except Exception as error:
            st.error(f'Upload failed: {error}')
    if sample_clicked:
        with Path('synthetic_sales_data.csv').open('rb') as source:
            st.session_state.pending_source = save_source(source, st.session_state.session_id)
        st.session_state.pending_name = 'synthetic_sales_data.csv'
    if pending_name := st.session_state.get('pending_name'):
        # Plain text keeps unusual filenames from being interpreted as Markdown.
        with st.container(border=True):
            st.markdown('**📄 Selected CSV file**')
            st.text(pending_name)
    active = st.session_state.get('dataset')
    path = st.session_state.get('pending_source') or (active.source if active else None)
    if path and not Path(path).is_file():
        st.warning('The retained source expired. Upload the CSV again to change columns.')
        st.session_state.pop('pending_source', None)
        path = None
    if path:
        available = inspect_header(path)
        fixed = [c for c in ALWAYS_LOAD_COLUMNS if c in available]
        st.caption('Always loaded: ' + (', '.join(fixed) or '(none present)'))
        missing = [c for c in ALWAYS_LOAD_COLUMNS if c not in available]
        if missing:
            st.caption('Fixed fields absent from this file: ' + ', '.join(missing))
        options = [c for c in available if c not in fixed]
        defaults = [c for c in (active.selected if active and active.source == path else []) if c in options]
        seconds_profile = None
        seconds_error = None
        if 'Seconds' in available:
            profile_key = f'home:seconds-profile:{path.stem}'
            if profile_key not in st.session_state:
                try:
                    st.session_state[profile_key] = inspect_numeric_range(path)
                except Exception as error:
                    st.session_state[profile_key] = error
            profile_result = st.session_state[profile_key]
            if isinstance(profile_result, Exception):
                seconds_error = str(profile_result)
            else:
                seconds_profile = profile_result
        with st.form(f'columns:{path.stem}'):
            seconds_range = None
            if seconds_profile and seconds_profile.minimum < seconds_profile.maximum:
                applied_range = (active.seconds_range if active and active.source == path
                                 and active.seconds_range else
                                 (seconds_profile.minimum, seconds_profile.maximum))
                # Form batching applies the interval and column projection in one parse.
                seconds_range = st.slider(
                    'Seconds interval', min_value=seconds_profile.minimum,
                    max_value=seconds_profile.maximum, value=applied_range,
                    step=seconds_profile.step, key=f'home:seconds:{path.stem}',
                    help='Only rows whose numeric Seconds value is inside this inclusive interval are loaded.',
                )
                if seconds_profile.invalid_rows:
                    st.caption(f'{seconds_profile.invalid_rows:,} rows with nonnumeric or missing Seconds values will be excluded.')
            elif seconds_profile:
                seconds_range = (seconds_profile.minimum, seconds_profile.maximum)
                st.caption(f'Only one numeric Seconds value is available: {seconds_profile.minimum:g}.')
            elif seconds_error:
                st.warning(seconds_error)
            extra = st.multiselect('Additional columns', options, default=defaults, key=f'home:extra:{path.stem}')
            parquet = st.checkbox('Use experimental Parquet cache', value=False,
                                  help='Off by default until benchmarks demonstrate a benefit.')
            apply = st.form_submit_button('Apply columns')
        if apply:
            try:
                candidate = load_dataset(path, st.session_state.get('pending_name', active.name if active else 'CSV'),
                                         fixed + extra, parquet, seconds_range)
                check_cancelled()  # A terminated session must not publish a late parse result.
                # Commit only after parsing succeeds; a failed import leaves the old view usable.
                reset_controls()
                st.session_state.update(dataset=candidate, df_full=candidate.frame)
                active = candidate
            except Exception as error:
                st.error(f'Import failed: {error}')
    if active:
        st.success(f'{active.name}: {len(active.frame):,} rows, {len(active.frame.columns):,} loaded fields')
        st.dataframe(active.frame.head(5))
        st.info('Use the sidebar to open Engineering Explorer or a compatible legacy page.')
