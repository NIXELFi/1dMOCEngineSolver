"""Allow running the GUI as a module: `python -m engine_simulator.gui`."""

import argparse

from engine_simulator.gui.server import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Engine Simulator GUI v1 — local FastAPI + React",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port to bind (default: 8765)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't auto-open the browser")

    args = parser.parse_args()
    main(host=args.host, port=args.port, open_browser=not args.no_browser)
