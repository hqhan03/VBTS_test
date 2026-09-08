#!/usr/bin/env python3
"""Figures for docs/force_estimation.md.

Two of them, and the second exists because of a standing instruction: gel
thickness and hardness are not variables to average over one at a time, so the
per-unit result is shown as a 3x3 grid rather than two marginal tables.

    scripts/make_force_figures.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402
from mpl_toolkits.mplot3d import Axes3D   # noqa: F401,E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "9DTact"
FIGS = ROOT / "docs" / "figures"
HARDS = ["soft", "medium", "hard"]
THICK = [1, 2, 3]


def label_noise():
    """MAE a perfect model would still show, from the F/T reading's own scatter.

    Second differences, which cancel the ramp's linear part; var = 6 sigma^2.
    A first difference would be dominated by the real force change between
    frames (0.048 N median) and overstate the noise by a factor of five.
    """
    out = {}
    for d in sorted((DATA / "20260907_passB_ball8").iterdir()):
        p = d / "stream" / "frames.csv"
        if not p.exists():
            continue
        s = pd.read_csv(p)
        fz = np.abs(s.Fz_s_corr.fillna(s.Fz_s).values)
        seg = s.segment.values
        k = (seg[2:] == seg[:-2]) & (seg[1:-1] == seg[:-2])
        d2 = (fz[2:] - 2 * fz[1:-1] + fz[:-2])[k]
        out[d.name.replace("9DTact_", "")] = 0.798 * np.median(np.abs(d2)) / 0.6745 / np.sqrt(6)
    return out


def fig_resolution(f, seed, floor, scalar):
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    w = sorted(f.width_px.unique())
    for s, g in f.groupby("sensor"):
        g = g.sort_values("width_px")
        ax.plot(g.width_px, g.fz_mae, color="0.75", lw=0.8, zorder=1)
    med = f.groupby("width_px").fz_mae.median().reindex(w)
    # the seed band: what one fit scatters by with everything else held fixed
    sd = seed.groupby(["sensor", "width_px"]).fz_mae.std(ddof=1).median()
    ax.fill_between(w, med - sd, med + sd, color="#4c72b0", alpha=.18, zorder=2,
                    label=f"seed-to-seed sd of one fit (±{sd:.3f} N)")
    ax.plot(w, med, "o-", color="#4c72b0", lw=2.2, ms=7, zorder=4,
            label="median of 17 units")
    ax.axhline(np.median(list(floor.values())), color="#c44e52", ls="--", lw=1.6,
               zorder=3, label=f"label noise floor ({np.median(list(floor.values())):.3f} N)")
    ax.axhline(scalar, color="#55a868", ls=":", lw=1.8, zorder=3,
               label=f"two scalars per frame ({scalar:.3f} N)")
    ax.axhline(1 / 16, color="0.4", ls="-.", lw=1.2, zorder=3,
               label="ATI Mini45 quoted Fz resolution (1/16 N)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(w)
    hgt = {int(a): int(b) for a, b in zip(f.width_px, f.height_px)}
    ax.set_xticklabels([f"{a}×{hgt[a]}" for a in w], rotation=45, ha="right", fontsize=8)
    ax.set_yticks([0.02, 0.03, 0.05, 0.08, 0.15, 0.3, 0.7])
    ax.set_yticklabels(["0.02", "0.03", "0.05", "0.08", "0.15", "0.30", "0.70"])
    ax.minorticks_off()
    ax.set_xlabel("input size the network sees")
    ax.set_ylabel("Fz MAE (N), held-out cycles")
    ax.set_title("Force estimation does not improve with camera resolution\n"
                 "17 units, one fit per cell — the spread between cells is the fit's own noise",
                 fontsize=10)
    ax.grid(alpha=.25, lw=.6)
    ax.legend(fontsize=8, framealpha=.9)
    fig.tight_layout()
    fig.savefig(FIGS / "force_vs_resolution.png", dpi=140)
    plt.close(fig)
    print(f"  -> {(FIGS/'force_vs_resolution.png').relative_to(ROOT)}")


def fig_grid(per):
    fig = plt.figure(figsize=(7.5, 5.5))
    ax = fig.add_subplot(111, projection="3d")
    cmap = plt.get_cmap("viridis_r")
    v = per.fz
    lo, hi = v.min(), v.max()
    for s, r in per.iterrows():
        xi = HARDS.index(s.split("_")[0])
        yi = THICK.index(int(s.split("_")[1][0]))
        rep = 0 if s.endswith("r1") else 1
        ax.bar3d(xi - .34 + .36 * rep, yi - .18, 0, .30, .36, r.fz,
                 color=cmap(0.15 + .75 * (r.fz - lo) / (hi - lo + 1e-12)),
                 edgecolor="0.25", lw=.4, shade=True)
    ax.set_xticks(range(3)); ax.set_xticklabels(HARDS)
    ax.set_yticks(range(3)); ax.set_yticklabels([f"{t} mm" for t in THICK])
    ax.set_xlabel("hardness"); ax.set_ylabel("gel thickness")
    ax.set_zlabel("Fz MAE (N)")
    ax.set_title("Force estimation error by gel\n(each cell: r1 left, r2 right; "
                 "median over the 12 input sizes)", fontsize=10)
    ax.view_init(elev=22, azim=-58)
    fig.tight_layout()
    fig.savefig(FIGS / "force3d_fz.png", dpi=140)
    plt.close(fig)
    print(f"  -> {(FIGS/'force3d_fz.png').relative_to(ROOT)}")


def main() -> int:
    f = pd.read_csv(DATA / "force_vs_resolution.csv")
    seed = pd.read_csv(DATA / "force_seed_study.csv")
    sc = pd.read_csv(DATA / "force_scalar_baseline.csv")
    floor = label_noise()
    per = f.groupby("sensor").agg(fz=("fz_mae", "median"), lat=("lat_mae", "median"),
                                  r2=("fz_r2", "median"), sd=("fz_mae", "std"),
                                  n=("fz_mae", "size"))
    per["se"] = per.sd / np.sqrt(per.n)
    FIGS.mkdir(parents=True, exist_ok=True)
    fig_resolution(f, seed, floor, float(sc.fz_mae.median()))
    fig_grid(per)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
