#!/usr/bin/env python3
"""Per-unit shear resolution requirement, from the 3-seed shear-knee sweeps.

Reads data/9DTact/shear_knee_{none,anti}.csv (17 units x 10 sizes x 3 seeds,
cycle split, block-separated metrics) and answers one question per unit: how
much shear accuracy is lost when the picture shrinks, and where the loss
starts. Two numbers per unit and per preprocessing:

  left arm   lat_mae_shear at 8x5 minus the unit's own best (3-seed means)
  knee       the smallest width at which the 3-seed mean is still within
             max(2 x seed sd, 15 %) of the unit's best, scanning leftwards
             from the best -- the resolution below which the unit degrades

Then: does either track gel hardness or thickness (Spearman), and a figure.
The RIGHT arm (overfitting at large inputs) is not in this sweep by design:
sizes stop at 854x480, where val/train is still ~1.
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import spearmanr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "9DTact"
FIGS = ROOT / "docs" / "figures"
HARD = {"soft": 0, "medium": 1, "hard": 2}


def per_unit(d):
    g = d.groupby(["sensor", "width_px"]).lat_mae_shear.agg(["mean", "std", "count"]).reset_index()
    rows = []
    for s, u in g.groupby("sensor"):
        u = u.sort_values("width_px")
        w = u.width_px.values; m = u["mean"].values; sd = np.nan_to_num(u["std"].values, nan=0.0)
        if len(w) < 4:
            continue
        ib = int(np.argmin(m)); best = m[ib]
        tol = max(2 * np.median(sd), 0.15 * best)
        knee = w[ib]
        for i in range(ib, -1, -1):
            if m[i] <= best + tol:
                knee = w[i]
            else:
                break
        name = s.replace("9DTact_", "")
        rows.append(dict(unit=name, hard=HARD[name.split("_")[0]],
                         th=int(name.split("_")[1][0]), best=best, w_best=w[ib],
                         at8=m[0], left=m[0] - best, knee=knee,
                         seed_sd=float(np.median(sd)), n_sizes=len(w),
                         n_seeds=int(u["count"].min())))
    return pd.DataFrame(rows)


def report(name, df):
    if df.empty:
        print(f"\n=== {name}: no unit has 4+ sizes yet ===")
        return
    print(f"\n=== {name}:  {len(df)} units,  seeds/cell >= {df.n_seeds.min()} ===")
    print(f"  {'unit':16s}{'hd':>3}{'th':>3}{'best':>8}{'@':>5}{'8x5':>8}{'left':>8}{'knee':>6}{'seed sd':>9}")
    for _, r in df.sort_values(["hard", "th"]).iterrows():
        print(f"  {r.unit:16s}{r.hard:3d}{r.th:3d}{r.best:8.4f}{r.w_best:5d}{r.at8:8.4f}"
              f"{r.left:8.4f}{r.knee:6d}{r.seed_sd:9.4f}")
    for col in ("left", "knee"):
        h = spearmanr(df.hard, df[col]); t = spearmanr(df.th, df[col])
        print(f"  {col:5s} hardness rho {h.statistic:+.3f} p {h.pvalue:.4f}   "
              f"thickness rho {t.statistic:+.3f} p {t.pvalue:.4f}")
    print("  knee by hardness (median):", df.groupby("hard").knee.median().to_dict(),
          "  by thickness:", df.groupby("th").knee.median().to_dict())
    print("  left by hardness (median):", df.groupby("hard").left.median().round(4).to_dict(),
          "  by thickness:", df.groupby("th").left.median().round(4).to_dict())


def figure(dd, out):
    fig, axes = plt.subplots(1, len(dd), figsize=(6.2 * len(dd), 4.4), squeeze=False)
    col = {0: "#4c72b0", 1: "#55a868", 2: "#c44e52"}; lab = {0: "soft", 1: "medium", 2: "hard"}
    for ax, (name, d) in zip(axes[0], dd.items()):
        g = d.groupby(["sensor", "width_px"]).lat_mae_shear.mean().reset_index()
        w = sorted(g.width_px.unique()); xi = {v: i for i, v in enumerate(w)}
        for s, u in g.groupby("sensor"):
            u = u.sort_values("width_px"); hd = HARD[s.replace("9DTact_", "").split("_")[0]]
            ax.plot([xi[v] for v in u.width_px], u.lat_mae_shear, "-", color=col[hd], alpha=.35, lw=1)
        for hd in (0, 1, 2):
            sel = g[g.sensor.str.contains(f"_{lab[hd]}_")]
            med = sel.groupby("width_px").lat_mae_shear.median().reindex(w)
            ax.plot(range(len(w)), med, "o-", color=col[hd], lw=2.4, ms=6, label=f"{lab[hd]} (median)")
        ax.set_xticks(range(len(w))); ax.set_xticklabels([str(v) for v in w], rotation=45, fontsize=8)
        ax.set_ylim(0, None); ax.set_xlim(-0.4, len(w) - 0.6); ax.grid(alpha=.25)
        ax.set_title(f"shear error vs input width -- {name}", fontsize=10.5)
        ax.set_xlabel("input width (px)"); ax.set_ylabel("shear |Fxy| MAE (N), shear-block test frames")
        ax.legend(fontsize=8.5, frameon=False)
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)
    print(f"  -> {out}")


if __name__ == "__main__":
    dd = {}
    for n in ("none", "anti"):
        f = DATA / f"shear_knee_{n}.csv"
        if f.exists():
            d = pd.read_csv(f)
            d = d[d.split == "cycle"]
            dd[n] = d
            report(n, per_unit(d))
    if dd and "--fig" in sys.argv:
        figure(dd, FIGS / "shear_knee.png")
