from __future__ import annotations

from flask import Flask

from . import create_app
from .config import Config
from .runtime_lease import acquire_runtime_state_lease


def create_runtime_app() -> Flask:
    """Create the browser app while retaining its shared state lease."""

    lease = acquire_runtime_state_lease(Config.DB_PATH)
    try:
        app = create_app()
    except BaseException:
        lease.close()
        raise
    app.extensions["runtime_state_lease"] = lease
    return app
