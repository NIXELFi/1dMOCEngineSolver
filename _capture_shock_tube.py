"""Capture the shock tube validation plot to PNG for visual review."""
import os
os.environ["MPLBACKEND"] = "Agg"

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pathlib import Path

OUT = Path("_plot_review")
OUT.mkdir(exist_ok=True)
OUT_PATH = OUT / "01_shock_tube.png"


def _save_show(*args, **kwargs):
    fig = plt.gcf()
    fig.savefig(OUT_PATH, dpi=110, bbox_inches="tight")
    print(f"  -> {OUT_PATH}")
    plt.close(fig)


plt.show = _save_show

from engine_simulator.validation.shock_tube import run_shock_tube

run_shock_tube(plot=True)
print(f"Saved: {OUT_PATH.resolve()}")
