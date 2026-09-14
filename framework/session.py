"""Atomic dataset lifecycle, operating only on the caller's session state."""
from pathlib import Path

from framework import data


def remove_source(source, session_id):
    """Delete a retained source and its caches, never a caller's original CSV."""
    if source is None:
        return
    path = Path(source)
    directory = (data.ROOT / session_id).resolve()
    if path.is_symlink() or path.resolve().parent != directory:
        return
    for retained in [path, *path.parent.glob(f'{path.stem}.*.parquet')]:
        # Windows may temporarily hold a handle; expiry cleanup can retry later.
        try:
            retained.unlink(missing_ok=True)
        except OSError:
            pass


@data.storage_operation
def stage_source(state, stream, name):
    """Validate a replacement before discarding the previous pending source."""
    path = data.save_source(stream, state['session_id'])
    previous = state.get('pending_source')
    active = state.get('dataset')
    state.update(pending_source=path, pending_name=name)
    if previous and (active is None or Path(previous) != active.source):
        remove_source(previous, state['session_id'])
    return path


@data.storage_operation
def commit_projection(state, selected, parquet=False):
    """All fallible parsing precedes the dataset swap and old-source cleanup."""
    previous = state.get('dataset')
    source = state.get('pending_source') or (previous.source if previous else None)
    name = state.get('pending_name') or (previous.name if previous else 'CSV')
    data.session_directory(state['session_id'])
    candidate = data.load_dataset(source, name, selected, parquet)
    # Renew after a long parse before committing, while cleanup is still excluded.
    data.session_directory(state['session_id'])
    state.update(dataset=candidate, df_full=candidate.frame)
    state.pop('pending_source', None)
    state.pop('pending_name', None)
    # Saved controls and exports refer to the previous projection, even on the same source.
    for key in list(state):
        if key.startswith(('widget:', 'value:', 'legacy:', 'export:')):
            del state[key]
    if previous is not None and previous.source != candidate.source:
        remove_source(previous.source, state['session_id'])
    return candidate
