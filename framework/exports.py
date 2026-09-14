"""Explicit, session-private CSV preparation with rerun-safe download controls."""
import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st


def export_identity(frame, version, context=(), *, include_values=False):
    # Immutable dataset versions make row identity sufficient for full-size exports.
    # Grid responses are bounded and may contain edits, so also hash their values.
    values = pd.util.hash_pandas_object(frame if include_values else frame.index, index=True)
    digest = hashlib.sha256(values.to_numpy().tobytes()).hexdigest()
    return (version, tuple(frame.columns), tuple(map(str, frame.dtypes)), repr(context), digest)


def render_csv_export(frame, *, page, prepare_label='Prepare CSV export',
                      download_label='⬇️ Download filtered data as CSV',
                      filename='filtered_sales_data.csv', context=(), include_values=False):
    key = f'export:{Path(page).stem}'
    dataset = st.session_state.get('dataset')
    version = dataset.version if dataset else id(st.session_state.get('df_full'))
    prepared = st.session_state.get(key)
    # No full-result serialization or hashing until the first explicit preparation.
    identity = export_identity(frame, version, context, include_values=include_values) if prepared else None
    if prepared and prepared['identity'] != identity:
        del st.session_state[key]
        prepared = None
    if st.button(prepare_label, key=f'prepare:{key}'):
        identity = export_identity(frame, version, context, include_values=include_values)
        prepared = {'identity': identity, 'bytes': frame.to_csv(index=False).encode('utf-8')}
        st.session_state[key] = prepared
    if prepared:
        st.download_button(download_label, prepared['bytes'], filename, 'text/csv',
                           key=f'download:{key}', on_click='ignore')


def shared_filter_context():
    """Include saved sales filters, excluding unrelated page widgets."""
    return sorted((key, value) for key, value in st.session_state.items()
                  if key.startswith('value:shared:'))
