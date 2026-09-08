#!/usr/bin/env python3
"""Compare principles gel by gel -- never as pooled averages.

A soft 1 mm gel and a hard 3 mm gel are different sensors whatever principle
reads them, so the only fair comparison is within one (hardness, thickness)
cell: the 9DTact units of that spec against the DIGIT units of that spec and
the DIGIT_Marker units of that spec. For each cell present in >= 2 principles
this draws Fz and shear MAE against input size, one curve per unit coloured by
principle, and prints the per-cell paired difference at each size.

Inputs: the 1-seed 12-size sweeps of each principle (9DTact force_vs_resolution_v2,
DIGIT(_Marker) force_vs_resolution_grey) -- same recipe, same batch, same
epochs, same split rule. Block metrics where present, blended otherwise (the
9DTact v2 sweep predates them; its 3-seed shear_knee sweep has them but stops
at 854 -- both are shown).
"""
import os, sys, argparse, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyse_saturation import load as load_sweep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, "data", *p)
COL = {"9DTact": "#4c72b0", "DIGIT": "#dd8452", "DIGIT_Marker": "#55a868"}
HN = {0: "soft", 1: "medium", 2: "hard"}

ap = argparse.ArgumentParser(); ap.add_argument("--chan", choices=["fz", "sh"], default="fz"); A = ap.parse_args()
CH = A.chan; CHN = {"fz": "Fz MAE (N)", "sh": "shear |Fxy| MAE (N)"}[CH]
srcs = {"9DTact": D("9DTact", "force_vs_resolution_v2.csv"),
        "DIGIT_Marker": D("DIGIT_Marker", "force_vs_resolution_grey.csv"),
        "DIGIT": D("DIGIT", "force_vs_resolution_grey.csv")}
frames = []
for pr, f in srcs.items():
    if os.path.exists(f):
        d = load_sweep(f); d["principle"] = pr; frames.append(d)
d = pd.concat(frames, ignore_index=True)
g = d.groupby(["principle", "unit", "hard", "th", "width_px"])[["fz", "sh"]].mean().reset_index()
w = sorted(g.width_px.unique()); X = {v: i for i, v in enumerate(w)}
cells = [(h, t) for t in (1, 2, 3) for h in (0, 1, 2)]
fig, axes = plt.subplots(3, 3, figsize=(15, 11), sharex=True, sharey=True)   # one y for all cells -- the point is comparability
print(f"  {'cell':14s}{'size':>6}  " + "  ".join(f"{p:>13s}" for p in srcs) + "   (median per principle)")
for k, (h, t) in enumerate(cells):
    ax = axes[t - 1][h]; sel = g[(g.hard == h) & (g.th == t)]
    prs = sel.principle.unique()
    for pr in prs:
        s = sel[sel.principle == pr]
        for u, x in s.groupby("unit"):
            x = x.sort_values("width_px"); ax.plot([X[v] for v in x.width_px], x[CH], "-", color=COL[pr], alpha=.35, lw=1)
        med = s.groupby("width_px")[CH].median().reindex(w)
        ax.plot([X[v] for v in w], med, "o-", color=COL[pr], lw=2.2, ms=5, label=f"{pr} (n={s.unit.nunique()})")
    ax.set_title(f"{HN[h]} {t} mm", fontsize=10.5); ax.grid(alpha=.25)
    ax.set_xticks(range(len(w))); ax.set_xticklabels([str(v) for v in w], rotation=60, fontsize=7)
    if prs.size: ax.legend(fontsize=8, frameon=False)
    if len(prs) >= 2:
        for wv in (8, 48, 160, 854, 1920):
            if wv in w:
                vals = {pr: sel[(sel.principle == pr) & (sel.width_px == wv)][CH].median() for pr in srcs}
                print(f"  {HN[h]+' '+str(t)+'mm':14s}{wv:>6}  " + "  ".join(f"{vals.get(pr, np.nan):13.4f}" for pr in srcs))
for ax in axes[:, 0]: ax.set_ylabel(CHN)
axes[0][0].set_ylim(0, 0.22 if CH == "fz" else 0.16)
fig.suptitle(f"{CHN.split(' (')[0]} against input size, gel by gel — one panel per (hardness, thickness), one colour per principle", fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.965)); out = os.path.join(ROOT, "docs", "figures", f"cross_principle_{CH}.png"); fig.savefig(out, dpi=130); plt.close(fig)
print("  ->", out)
