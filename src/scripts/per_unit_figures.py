#!/usr/bin/env python3
"""One panel per sensor: force error against input size, both channels.

The 9DTact study drew this for Fz alone (make_force_figures.fig_per_unit). Here
both channels go in one panel per unit, because the interesting thing on DIGIT
is that they disagree -- Fz is flat over a decade of sizes while shear has a
minimum -- and putting them side by side per unit shows whether that holds for
every gel or only in the median.

Panels are laid out as the design: columns soft / medium / hard, rows 1 mm r1,
1 mm r2, 2 mm r1, ... Axes are shared, y is LINEAR and x is CATEGORICAL (the
sizes are not on a linear scale and drawing them as if they were misleads).
Where a cell has three seeds the band shows their spread.

  per_unit_figures.py <csv> <label> [out.png]
"""
import sys, re
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIGS = ROOT / "docs" / "figures"
HARDS = ["soft", "medium", "hard"]
THICK = [1, 2, 3]
C_FZ, C_SH = "#22303f", "#c44e52"


def draw(csv, label, out):
    d = pd.read_csv(csv)
    w = sorted(d.width_px.unique())
    xi = {v: i for i, v in enumerate(w)}
    hgt = {int(a): int(b) for a, b in zip(d.width_px, d.height_px)}
    order = [f"{h}_{t}mm_{r}" for t in THICK for r in ("r1", "r2") for h in HARDS]
    fig, axes = plt.subplots(6, 3, figsize=(11.5, 13.5), sharex=True, sharey=True)
    for ax, s in zip(axes.ravel(), order):
        g = d[d.sensor == s]
        if not len(g):
            ax.axis("off"); continue
        for col, colour, nm in ((("fz_mae_normal"), C_FZ, "Fz (normal block)"),
                                (("lat_mae_shear"), C_SH, "shear (shear block)")):
            m = g.groupby("width_px")[col].median().sort_index()
            lo = g.groupby("width_px")[col].min().sort_index()
            hi = g.groupby("width_px")[col].max().sort_index()
            x = [xi[v] for v in m.index]
            ax.fill_between(x, lo.values, hi.values, color=colour, alpha=.16, lw=0)
            ax.plot(x, m.values, "o-", color=colour, lw=1.5, ms=4.2, label=nm)
        ax.set_title(s, fontsize=9.5, pad=4)
        ax.grid(alpha=.22, lw=.5)
    for ax in axes.ravel():
        ax.set_xticks(range(len(w)))
        ax.set_xlim(-0.4, len(w) - 0.6)
        ax.set_ylim(0, None)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
        ax.minorticks_off()
    for ax in axes[-1]:
        ax.set_xticklabels([f"{a}×{hgt[a]}" for a in w], rotation=90, fontsize=7)
    for r in range(6):
        axes[r][0].set_ylabel("MAE (N)", fontsize=9)
    h, lb = axes[0][0].get_legend_handles_labels()
    fig.legend(h, lb, loc="upper center", ncol=2, fontsize=9.5, frameon=False,
               bbox_to_anchor=(0.5, 0.972))
    fig.suptitle(f"{label} — force-estimation error against input size, one panel per unit\n"
                 "columns: soft / medium / hard   ·   rows: 1 mm r1, r2, 2 mm r1, r2, "
                 "3 mm r1, r2   ·   band = seed spread   ·   shared axes, linear y",
                 fontsize=11.5, y=0.995)
    fig.supxlabel("input size the network sees", fontsize=10)
    fig.tight_layout(rect=(0, 0.012, 1, 0.955))
    fig.savefig(FIGS / out, dpi=140)
    plt.close(fig)
    print(f"  -> docs/figures/{out}")


if __name__ == "__main__":
    draw(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3
         else f"per_unit_{sys.argv[2]}.png")
