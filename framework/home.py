"""Shared upload page for both historical entry points."""
from pathlib import Path
import os
import shutil
import uuid
import streamlit as st
from framework.config import ALWAYS_LOAD_COLUMNS, MAX_UPLOAD_MB
from framework.data import cleanup, save_source, inspect_header, load_dataset, session_directory
from framework.state import reset_controls


def render():
    st.set_page_config(page_title='Engineering Data Dashboard', layout='wide')
    st.title('Engineering Data Dashboard')
    cleanup()
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    session_directory(st.session_state.session_id)
    if st.button('Clear dataset'):
        shutil.rmtree(session_directory(st.session_state.session_id), ignore_errors=True)
        st.session_state.clear()
        st.rerun()
    uploaded = st.file_uploader('Drop a CSV here', type=['csv'],
                               max_upload_size=MAX_UPLOAD_MB)
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
    if os.environ.get('DASHBOARD_SAMPLE') == '1' and st.button('Load sample data'):
        with Path('synthetic_sales_data.csv').open('rb') as source:
            st.session_state.pending_source = save_source(source, st.session_state.session_id)
        st.session_state.pending_name = 'synthetic_sales_data.csv'
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
        with st.form(f'columns:{path.stem}'):
            extra = st.multiselect('Additional columns', options, default=defaults, key=f'home:extra:{path.stem}')
            parquet = st.checkbox('Use experimental Parquet cache', value=False,
                                  help='Off by default until benchmarks demonstrate a benefit.')
            apply = st.form_submit_button('Apply columns')
        if apply:
            try:
                candidate = load_dataset(path, st.session_state.get('pending_name', active.name if active else 'CSV'), fixed + extra, parquet)
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
