"""FastAPI app for the engine simulator GUI.

Owns the FastAPI instance, the ASGI lifespan (which initializes the
SweepManager), and the browser launch helper. Imports route modules
for their side effect of registering endpoints.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


logger = logging.getLogger(__name__)


# Module-level singleton — set during the lifespan startup. Other modules
# (routes_api, routes_ws) import this to access the SweepManager.
sweep_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """ASGI lifespan: starts the SweepManager on startup, cleans up on shutdown."""
    global sweep_manager
    import asyncio

    loop = asyncio.get_running_loop()
    sweeps_dir = str(Path(__file__).resolve().parents[2] / "sweeps")

    try:
        from engine_simulator.gui.sweep_manager import SweepManager
        from engine_simulator.gui.routes_ws import broadcast
        sweep_manager = SweepManager(
            loop=loop,
            sweeps_dir=sweeps_dir,
            broadcast_fn=broadcast,
        )
    except ImportError:
        logger.warning("SweepManager not yet available; running in skeleton mode")
        sweep_manager = None

    yield

    if sweep_manager is not None and sweep_manager.current is not None and sweep_manager.current.status == "running":
        await sweep_manager.stop_sweep()


def create_app() -> FastAPI:
    """Construct the FastAPI app with all routes registered."""
    app = FastAPI(
        title="Engine Simulator GUI",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Routes are registered by importing their modules. We do this here
    # rather than at module load to control the import order.
    from engine_simulator.gui import routes_api  # noqa: F401
    from engine_simulator.gui import routes_ws   # noqa: F401

    app.include_router(routes_api.router)
    app.include_router(routes_ws.router)

    # Static files: pre-built React bundle
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def open_browser_after_delay(url: str, delay: float = 1.0):
    """Open the user's default browser to `url` after a short delay,
    so the server has time to bind the port first."""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    """Entry point: start uvicorn and (optionally) open the browser."""
    import uvicorn

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    url = f"http://{host}:{port}/"
    logger.info(f"Server starting on {url}")

    if open_browser:
        open_browser_after_delay(url)

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")
