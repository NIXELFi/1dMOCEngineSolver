#!/usr/bin/env python3
"""Build the React frontend and copy the dist/ output into the Python package.

Usage:
    python scripts/build_gui.py

This runs `npm run build` in gui-frontend/, then copies the generated
dist/ contents into engine_simulator/gui/static/. The Python package
ships with the pre-built bundle inside it; end users don't need Node.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    frontend_dir = repo_root / "gui-frontend"
    dist_dir = frontend_dir / "dist"
    static_dir = repo_root / "engine_simulator" / "gui" / "static"

    if not frontend_dir.exists():
        print(f"ERROR: {frontend_dir} does not exist", file=sys.stderr)
        return 1

    # Ensure ~/.local/node/bin is on PATH so npm can find node
    env = os.environ.copy()
    node_bin = Path.home() / ".local" / "node" / "bin"
    if node_bin.exists():
        env["PATH"] = f"{node_bin}:{env.get('PATH', '')}"

    print(f"Running 'npm run build' in {frontend_dir}...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(frontend_dir),
        env=env,
        check=False,
    )
    if result.returncode != 0:
        print("ERROR: npm build failed", file=sys.stderr)
        return result.returncode

    if not dist_dir.exists():
        print(f"ERROR: Expected build output {dist_dir} not found", file=sys.stderr)
        return 1

    # Wipe static_dir, then copy dist contents in
    if static_dir.exists():
        for item in static_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    static_dir.mkdir(parents=True, exist_ok=True)

    for item in dist_dir.iterdir():
        dest = static_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    print(f"Built frontend bundle copied to {static_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
