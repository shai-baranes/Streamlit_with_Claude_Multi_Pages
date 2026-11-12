"""Report dashboard interactions without sending widget values or rerunning pages."""
import os
import re
from pathlib import Path

import streamlit as st
from starlette.responses import JSONResponse


@st.cache_resource
def _reporter():
    # The renderer is shared; credentials are supplied per mount.
    source = Path(__file__).with_name('admin_assets') / 'activity.js'
    return st.components.v2.component(
        'admin_activity_reporter', html='<span hidden></span>',
        js=source.read_text(encoding='utf-8'),
    )


def mount_reporter():
    from streamlit import runtime
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    from framework.admin_runtime import shared_adapter

    ctx = get_script_run_ctx()
    if ctx is None or not runtime.exists():
        return
    # Streamlit replaces the cursor map on each script execution. Pages may
    # reach this hook through both ui() and require_data().
    if getattr(ctx, '_admin_reporter_cursors', None) is ctx.cursors:
        return
    adapter = shared_adapter(runtime.get_instance())
    token = adapter.call('register_activity', ctx.session_id)
    if token:
        ctx._admin_reporter_cursors = ctx.cursors
        _reporter()(data={'token': token}, key='_admin_activity_reporter')


async def report(request):
    if os.environ.get('DASHBOARD_ADMIN') != '1':
        return JSONResponse({'error': 'Activity tracking is disabled.'}, status_code=404)
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme}://{request.url.netloc}':
        return JSONResponse({'error': 'Invalid origin.'}, status_code=403)
    token = request.headers.get('x-dashboard-activity', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return JSONResponse({'error': 'Invalid activity credential.'}, status_code=400)

    from starlette.responses import Response
    from streamlit.runtime import get_instance
    from framework.admin_runtime import shared_adapter

    adapter = shared_adapter(get_instance())
    if not adapter.report_activity(token):
        return JSONResponse({'error': 'Unknown activity credential.'}, status_code=403)
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})
