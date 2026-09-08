#!/usr/bin/env python3
"""Scatter panels for the pre-registered hypotheses in docs/cross_principle.md 2.

Reads data/derived_with_performance.csv (written by correlations.py). One panel
per hypothesis, one marker shape per principle, Spearman within each principle
printed in the legend, plus the rank-partial rho controlling for principle.
Nothing pooled across principles is drawn as a fit line.
"""
import os, numpy as np, pandas as pd
from scipy.stats import spearmanr
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
df = pd.read_csv(os.path.join(ROOT, "data", "derived_with_performance.csv"))
COL = {"9DTact": "#4c72b0", "DIGIT_Marker": "#55a868", "DIGIT": "#dd8452"}
MK = {"9DTact": "o", "DIGIT_Marker": "s", "DIGIT": "^"}
H = [("H1", "img_slope_lvl_per_N", "fz_best", "image response (lvl / N)", "Fz best MAE (N)"),
     ("H2", "lat_noise_mae", "sh_best", "shear label noise floor (N)", "shear best MAE (N)"),
     ("H2b", "lat_rate_per_frame", "sh_best", "shear label change per frame (N)", "shear best MAE (N)"),
     ("H2c", "lat_sd_0N", "sh_best", "F/T lateral noise at 0 N (N)", "shear best MAE (N)"),
     ("H3", "bw_shear_f90", "sh_knee", "shear-signature bandwidth (cyc/mm)", "shear knee (px)"),
     ("H4", "a_2N_mm", "fz_knee", "contact radius at 2 N (mm)", "Fz knee (px)"),
     ("H5", "hertz_k", "sh_res_loss", "Hertz k (ball4)", "shear resolution loss (N)"),
     ("H6", "pedestal_ratio", "fz_best", "probe-shadow pedestal (ref/collect)", "Fz best MAE (N)"),
     ("H7", "img_resp_at_2N", "fz_best", "image response at 2 N (lvl)", "Fz best MAE (N)")]


def partial(s, x, y):
    rx = s[x].rank() - s[x].rank().groupby(s.principle).transform("mean")
    ry = s[y].rank() - s[y].rank().groupby(s.principle).transform("mean")
    return spearmanr(rx, ry)


fig, axes = plt.subplots(3, 3, figsize=(15, 12))
for ax, (hid, x, y, xl, yl) in zip(axes.ravel(), H):
    s = df[[x, y, "principle", "unit"]].dropna()
    for pr, g in s.groupby("principle"):
        r = spearmanr(g[x], g[y]) if len(g) >= 6 else None
        lab = f"{pr} n={len(g)}" + (f"  rho {r.statistic:+.2f} p {r.pvalue:.3f}" if r else "")
        ax.scatter(g[x], g[y], color=COL[pr], marker=MK[pr], s=42, alpha=.85, label=lab, edgecolor="k", linewidth=.4)
    if s.principle.nunique() >= 2 and len(s) >= 8:
        pr_ = partial(s, x, y); ax.set_title(f"{hid}: partial rho (principle out) {pr_.statistic:+.2f}, p {pr_.pvalue:.3f}", fontsize=9.5)
    else:
        ax.set_title(hid, fontsize=9.5)
    ax.set_xlabel(xl, fontsize=9); ax.set_ylabel(yl, fontsize=9); ax.grid(alpha=.25); ax.legend(fontsize=7, frameon=False)
    if "knee" in y: ax.set_yscale("log", base=2); ax.set_yticks([8, 16, 32, 48, 80, 160, 320, 854]); ax.set_yticklabels([8, 16, 32, 48, 80, 160, 320, 854])
fig.suptitle("Pre-registered hypotheses (docs/cross_principle.md 2) — one point per unit, one marker per principle", fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.96)); out = os.path.join(ROOT, "docs", "figures", "hypotheses.png"); fig.savefig(out, dpi=130); plt.close(fig)
print("  ->", out)
