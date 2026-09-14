"""Widget values are copied into non-widget state before navigation cleanup."""
from pathlib import Path
import streamlit as st

WIDGETS = {'checkbox', 'toggle', 'selectbox', 'multiselect', 'slider', 'radio',
           'number_input', 'text_input', 'date_input'}

class PersistentUI:
    def __init__(self, target, scope):
        self.target, self.scope = target, scope
        self.in_form = False

    def __getattr__(self, name):
        if name == 'cache_data':
            # Legacy decorators cached entire private frames process-wide. Source projections
            # now live in session state, so these small transforms need no shared cache.
            def uncached(function=None, **options):
                return function if function is not None else (lambda function: function)
            return uncached
        if name == 'dataframe':
            def dataframe(data=None, *args, **kwargs):
                from framework.config import MAX_PREVIEW
                if hasattr(data, 'head') and len(data) > MAX_PREVIEW:
                    self.target.caption(f'Preview limited to {MAX_PREVIEW:,} rows.')
                    data = data.head(MAX_PREVIEW)
                return self.target.dataframe(data, *args, **kwargs)
            return dataframe
        if name == 'form':
            from contextlib import contextmanager
            @contextmanager
            def form(*args, **kwargs):
                with self.target.form(*args, **kwargs):
                    self.in_form = True
                    try:
                        yield
                    finally:
                        self.in_form = False
            return form
        if name == "session_state":
            return ScopedState(self.scope)
        method = getattr(self.target, name)
        if name not in WIDGETS:
            return method
        def widget(label, *args, **kwargs):
            scope = 'shared' if self.scope == 'utils' else self.scope
            identity = kwargs.get('key', label)
            key = f'widget:{scope}:{identity}'
            saved = f'value:{scope}:{identity}'
            callback = kwargs.pop('on_change', None)
            callback_args = kwargs.pop('args', ())
            callback_kwargs = kwargs.pop('kwargs', {})
            original_key = kwargs.get('key')
            if key not in st.session_state:
                if saved in st.session_state:
                    st.session_state[key] = st.session_state[saved]
                elif original_key and original_key in ScopedState(self.scope):
                    st.session_state[key] = ScopedState(self.scope)[original_key]
            # Option lists can shrink after filtering or changing a grouping field.
            options = kwargs.get('options', args[0] if args else None)
            if key in st.session_state and name in {'multiselect', 'selectbox', 'radio'} and options is not None:
                current = st.session_state[key]
                if name == 'multiselect':
                    st.session_state[key] = [v for v in current if v in options]
                elif current not in options and len(options):
                    st.session_state[key] = list(options)[0]
            if key in st.session_state and name in {'slider', 'number_input'}:
                lower = kwargs.get('min_value', args[0] if args else None)
                upper = kwargs.get('max_value', args[1] if len(args) > 1 else None)
                def clamp(value):
                    if value is None:
                        return value
                    if lower is not None:
                        value = max(lower, value)
                    if upper is not None:
                        value = min(upper, value)
                    return value
                current = st.session_state[key]
                st.session_state[key] = tuple(clamp(v) for v in current) if isinstance(current, (tuple, list)) else clamp(current)
            def changed():
                st.session_state[saved] = st.session_state[key]
                if original_key:
                    ScopedState(self.scope)[original_key] = st.session_state[key]
                if callback:
                    callback(*callback_args, **callback_kwargs)
            kwargs.update(key=key)
            if not self.in_form:
                kwargs["on_change"] = changed
            value = method(label, *args, **kwargs)
            st.session_state[saved] = value
            if original_key:
                ScopedState(self.scope)[original_key] = value
            return value
        return widget


def ui(file):
    # Metadata only: administration does not cache private page data.
    from framework.admin_runtime import activity
    activity(file)
    return PersistentUI(st, Path(file).stem)


def reset_controls():
    for key in list(st.session_state):
        if key.startswith(('widget:', 'value:', 'legacy:')):
            del st.session_state[key]

# Legacy callbacks access session_state directly; map their page-local keys too.
from collections.abc import MutableMapping
class ScopedState(MutableMapping):
    shared = {'session_id', 'dataset', 'df_full', 'pending_source', 'pending_name', 'upload_id'}
    def __init__(self, scope):
        object.__setattr__(self, 'scope', scope)
    def key(self, key):
        return key if key in self.shared else f'legacy:{self.scope}:{key}'
    def __getitem__(self, key): return st.session_state[self.key(key)]
    def __setitem__(self, key, value): st.session_state[self.key(key)] = value
    def __delitem__(self, key): del st.session_state[self.key(key)]
    def __iter__(self):
        prefix = f'legacy:{self.scope}:'
        return iter([k if k in self.shared else k[len(prefix):] for k in st.session_state if k in self.shared or k.startswith(prefix)])
    def __len__(self): return sum(1 for _ in self)
    def __getattr__(self, key): return self[key]
    def __setattr__(self, key, value): self[key] = value
