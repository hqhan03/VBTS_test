#!/usr/bin/env python3
"""Where does force-estimation error saturate, per gel thickness and hardness?

Works on any force-vs-resolution sweep CSV (9DTact or DIGIT_Marker; one or
several seeds). For each unit and each channel it reads the error curve over
input size, takes per-size means over seeds, and reports

  best      the smallest error over sizes, and the size it occurs at
  res_loss  error at the smallest size minus best (what shrinking costs)
  knee      the smallest width still within max(2 x seed sd, 15 % of best) of
            the best, scanning leftwards from the best -- the size below which
            the unit degrades. With one seed the tolerance is 15 % only and the
            knee is provisional.

Channels: Fz uses `fz_mae_normal` (normal-block test frames) when present,
else `fz_mae`; shear uses `lat_mae_shear` (shear-block frames) when present,
else `lat_mae`. Groups by hardness and thickness with Spearman tests, and
draws a 2 x 2 figure: rows Fz / shear, columns median-by-hardness /
median-by-thickness, thin lines per unit, linear y, evenly spaced x.

    python3 scripts/analyse_saturation.py data/DIGIT_Marker/force_vs_resolution_grey.csv \
        --label DIGIT_Marker --fig docs/figures/saturation_DIGIT_Marker_grey.png
"""
import argparse
import re
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HARD = {"soft": 0, "medium": 1, "hard": 2}
HNAME = {0: "soft", 1: "medium", 2: "hard"}
HCOL = {0: "#4c72b0", 1: "#55a868", 2: "#c44e52"}
TCOL = {1: "#8172b2", 2: "#ccb974", 3: "#64b5cd"}


def unit_name(s):
    s = re.sub(r"^(9DTact|DIGIT_Marker|DIGIT)_", "", str(s))
    return re.sub(r"__\d+$", "", s)


def load(path):
    d = pd.read_csv(path)
    if "split" in d.columns:
        d = d[d.split == "cycle"]
    d = d.copy()
    d["unit"] = d.sensor.map(unit_name)
    d["hard"] = d.unit.str.split("_").str[0].map(HARD)
    d["th"] = d.unit.str.extract(r"(\d)mm").astype(int)[0]
    d["fz"] = d["fz_mae_normal"] if "fz_mae_normal" in d.columns else d["fz_mae"]
    d["sh"] = d["lat_mae_shear"] if "lat_mae_shear" in d.columns else d["lat_mae"]
    return d


def per_unit(d, col):
    g = d.groupby(["unit", "width_px"])[col].agg(["mean", "std", "count"]).reset_index()
    rows = []
    for u, x in g.groupby("unit"):
        x = x.sort_values("width_px")
        w = x.width_px.values; m = x["mean"].values
        sd = np.nan_to_num(x["std"].values, nan=0.0)
        if len(w) < 4:
            continue
        ib = int(np.argmin(m)); best = m[ib]
        tol = max(2 * float(np.median(sd)), 0.15 * best)
        knee = w[ib]
        for i in range(ib, -1, -1):
            if m[i] <= best + tol:
                knee = w[i]
            else:
                break
        rows.append(dict(unit=u, hard=HARD[u.split("_")[0]], th=int(u.split("_")[1][0]),
                         best=best, w_best=int(w[ib]), at_min=m[0], res_loss=m[0] - best,
                         knee=int(knee), seed_sd=float(np.median(sd)), n_seeds=int(x["count"].min())))
    return pd.DataFrame(rows)


def report(label, chan, df):
    print(f"\n=== {label} -- {chan}: {len(df)} units, seeds/cell >= {df.n_seeds.min()} ===")
    print(f"  {'unit':16s}{'hd':>3}{'th':>3}{'best':>8}{'@':>6}{'smallest':>9}{'res_loss':>9}{'knee':>6}{'seed sd':>9}")
    for _, r in df.sort_values(["hard", "th"]).iterrows():
        print(f"  {r.unit:16s}{r.hard:3d}{r.th:3d}{r.best:8.4f}{r.w_best:6d}{r.at_min:9.4f}"
              f"{r.res_loss:9.4f}{r.knee:6d}{r.seed_sd:9.4f}")
    for col in ("res_loss", "knee", "best"):
        h = spearmanr(df.hard, df[col]); t = spearmanr(df.th, df[col])
        print(f"  {col:8s} hardness rho {h.statistic:+.3f} p {h.pvalue:.4f}   "
              f"thickness rho {t.statistic:+.3f} p {t.pvalue:.4f}")
    print("  knee median   by hardness", df.groupby("hard").knee.median().to_dict(),
          " by thickness", df.groupby("th").knee.median().to_dict())
    print("  res_loss med. by hardness", df.groupby("hard").res_loss.median().round(4).to_dict(),
          " by thickness", df.groupby("th").res_loss.median().round(4).to_dict())
    print("  best median   by hardness", df.groupby("hard").best.median().round(4).to_dict(),
          " by thickness", df.groupby("th").best.median().round(4).to_dict())


def figure(d, label, out):
    w = sorted(d.width_px.unique()); X = list(range(len(w))); xi = {v: i for i, v in enumerate(w)}
    hgt = {int(a): int(b) for a, b in zip(d.width_px, d.height_px)} if "height_px" in d.columns else {}
    lab = [f"{v}×{hgt[v]}" if v in hgt else str(v) for v in w]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.6))
    for r, (col, cname) in enumerate([("fz", "Fz MAE (N)"), ("sh", "shear |Fxy| MAE (N)")]):
        g = d.groupby(["unit", "width_px"])[col].mean().reset_index()
        g["hard"] = g.unit.str.split("_").str[0].map(HARD)
        g["th"] = g.unit.str.extract(r"(\d)mm").astype(int)[0]
        for c, (key, cols, names) in enumerate([("hard", HCOL, HNAME), ("th", TCOL, {1: "1 mm", 2: "2 mm", 3: "3 mm"})]):
            ax = axes[r][c]
            for u, x in g.groupby("unit"):
                x = x.sort_values("width_px")
                ax.plot([xi[v] for v in x.width_px], x[col], "-", color=cols[int(x[key].iloc[0])], alpha=.3, lw=1)
            for k in sorted(cols):
                sel = g[g[key] == k]
                if sel.empty:
                    continue
                med = sel.groupby("width_px")[col].median().reindex(w)
                ax.plot(X, med, "o-", color=cols[k], lw=2.4, ms=6,
                        label=f"{names[k]} (median of {sel.unit.nunique()})")
            ax.set_xticks(X); ax.set_xticklabels(lab, rotation=45, ha="right", fontsize=8)
            ax.set_xlim(-0.4, len(w) - 0.6); ax.set_ylim(0, None); ax.grid(alpha=.25)
            ax.set_ylabel(cname); ax.legend(fontsize=8.5, frameon=False)
            ax.set_title(f"{label}: {cname.split(' ')[0]} by {'hardness' if key == 'hard' else 'thickness'}", fontsize=10.5)
    axes[1][0].set_xlabel("input size"); axes[1][1].set_xlabel("input size")
    fig.suptitle(f"{label} — force-estimation error against input size, one curve per unit, medians by gel", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.965)); fig.savefig(out, dpi=140); plt.close(fig)
    print(f"  -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--label", default="")
    ap.add_argument("--fig", default=None)
    a = ap.parse_args()
    d = load(a.csv)
    label = a.label or a.csv
    for chan, col in (("Fz", "fz"), ("shear", "sh")):
        df = per_unit(d, col)
        if not df.empty:
            report(label, chan, df)
    if a.fig:
        figure(d, label, a.fig)
