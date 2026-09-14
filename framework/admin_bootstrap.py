"""Start the optional admin listener in the same process as Streamlit."""
import os
import threading
from framework.admin_server import AdminServer
from framework.admin_runtime import RuntimeAdapter


def main():
    server = AdminServer(int(os.environ['DASHBOARD_ADMIN_PORT']))
    stopped = threading.Event()
    def attach():
        from streamlit import runtime
        while not stopped.wait(0.25):
            if runtime.exists() and runtime.get_instance()._async_objs is not None:
                try:
                    server.adapter = RuntimeAdapter(runtime.get_instance(), server.audit)
                except Exception as error:
                    server.error = f'Unsupported Streamlit runtime: {error}'
                    return
                break
        while not stopped.wait(5):
            try:
                server.adapter.call('snapshot')
            except Exception:
                server.audit.exception('monitor refresh failed')
    threading.Thread(target=attach, daemon=True).start()
    try:
        from streamlit.web.cli import main as streamlit_main
        streamlit_main()
    finally:
        stopped.set()
        server.close()


if __name__ == '__main__':
    main()
