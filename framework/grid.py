"""Page browser payloads while keeping a selected source row visible on expansion."""
from pathlib import Path
import inspect
import math
from st_aggrid import AgGrid as original_aggrid
from framework.config import MAX_PREVIEW
from framework.state import ui


def AgGrid(data, *args, **kwargs):
    selected_source_row = kwargs.pop('selected_source_row', None)
    if len(data) > MAX_PREVIEW:
        options = dict(kwargs.get('gridOptions') or {})
        selected = options.get('preSelectedRows') or [0]
        index = int(selected[0])
        if selected_source_row is not None and '_source_row' in data:
            matches = data['_source_row'].astype(str).eq(str(selected_source_row)).to_numpy().nonzero()[0]
            if len(matches):
                index = int(matches[0])
        # A mode remount gets a fresh page default containing the previously selected row.
        caller = Path(inspect.currentframe().f_back.f_code.co_filename)
        controls = ui(caller)
        page = controls.number_input('Grid page', min_value=1,
                                     max_value=math.ceil(len(data) / MAX_PREVIEW),
                                     value=index // MAX_PREVIEW + 1,
                                     key=f'grid_page:{kwargs.get("key", "grid")}')
        start = (page - 1) * MAX_PREVIEW
        data = data.iloc[start:start + MAX_PREVIEW]
        if options.get('preSelectedRows'):
            options['preSelectedRows'] = [index - start] if start <= index < start + len(data) else []
        kwargs['gridOptions'] = options
        controls.caption(f'Grid preview: source view rows {start + 1:,}–{start + len(data):,}. Change Grid page to inspect other rows.')
    return original_aggrid(data, *args, **kwargs)
