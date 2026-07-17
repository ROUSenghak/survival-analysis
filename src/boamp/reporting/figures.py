"""Shared figure helpers: consistent style, PNG+PDF pair saving."""

from __future__ import annotations

import sys

import matplotlib

if "ipykernel" not in sys.modules:
    # headless (scripts, nbconvert without kernel display): use a non-GUI backend;
    # inside Jupyter keep the inline backend so plots render in the notebook
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def setup_style() -> None:
    plt.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": 200,
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
    })


def save_figure(fig, name: str, cfg) -> list[str]:
    """Save PNG + PDF pair to reports/figures/. Returns the paths."""
    out_dir = cfg.paths.reports_figures
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("png", "pdf"):
        p = out_dir / f"{name}.{ext}"
        fig.savefig(p, bbox_inches="tight")
        paths.append(str(p))
    plt.close(fig)
    return paths
