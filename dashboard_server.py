"""Serve the dashboard and Windows client upload route on one port."""
from contextlib import asynccontextmanager
import shutil

import anyio
import streamlit as st
from starlette.routing import Route

from framework import client_upload


@asynccontextmanager
async def lifespan(_app):
    store = await anyio.to_thread.run_sync(client_upload.start_staging)
    client_upload.staging = store

    async def expire_uploads():
        while True:
            await anyio.sleep(30)
            await anyio.to_thread.run_sync(store.sweep)
            from streamlit import runtime
            if runtime.exists() and runtime.get_instance()._async_objs is not None:
                store.reap_sessions(client_upload.controller())

    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(expire_uploads)
            try:
                yield
            finally:
                tasks.cancel_scope.cancel()
    finally:
        client_upload.staging = None
        await anyio.to_thread.run_sync(shutil.rmtree, store.directory, True)


app = st.App("Load CSV.py", routes=[
    Route('/api/client-load-csv', client_upload.upload_csv, methods=['POST']),
    Route('/api/client-stop-sessions', client_upload.stop_sessions, methods=['POST']),
], lifespan=lifespan)
