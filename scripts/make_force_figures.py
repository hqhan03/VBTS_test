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
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator          # noqa: E402
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402
from mpl_toolkits.mplot3d import Axes3D   # noqa: F401,E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "9DTact"
FIGS = ROOT / "docs" / "figures"
HARDS = ["soft", "medium", "hard"]
THICK = [1, 2, 3]


def label_noise(axis="fz"):
    """MAE a perfect model would still show, from the F/T reading's own scatter.

    Second differences, which cancel the ramp's linear part; var = 6 sigma^2.
    A first difference would be dominated by the real force change between
    frames (0.048 N median) and overstate the noise by a factor of five.

    `axis` is "fz" for the normal force or "lat" for the shear magnitude
    hypot(Fx, Fy), which is the quantity `lat_mae` scores.
    """
    out = {}
    for d in sorted((DATA / "20260907_passB_ball8").iterdir()):
        p = d / "stream" / "frames.csv"
        if not p.exists():
            continue
        s = pd.read_csv(p)
        if axis == "fz":
            v = np.abs(s.Fz_s_corr.fillna(s.Fz_s).values)
        else:
            v = np.hypot(s.Fx_s_corr.fillna(s.Fx_s).values,
                         s.Fy_s_corr.fillna(s.Fy_s).values)
        seg = s.segment.values
        k = (seg[2:] == seg[:-2]) & (seg[1:-1] == seg[:-2])
        d2 = (v[2:] - 2 * v[1:-1] + v[:-2])[k]
        out[d.name.replace("9DTact_", "")] = 0.798 * np.median(np.abs(d2)) / 0.6745 / np.sqrt(6)
    return out


def fig_resolution(f, seed, floor, scalar, col="fz_mae", name="Fz", out="force_vs_resolution.png"):
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    w = sorted(f.width_px.unique())
    # x is CATEGORICAL and evenly spaced (operator, 2026-09-08). The twelve
    # sizes are a ladder, not samples of a continuous variable, and a log x
    # crowded the four largest into the right-hand fifth of the plot -- which
    # reads as a log axis even after the y was made linear.
    xi = {v: i for i, v in enumerate(w)}
    for s, g in f.groupby("sensor"):
        g = g.sort_values("width_px")
        ax.plot([xi[v] for v in g.width_px], g[col], color="0.75", lw=0.8, zorder=1)
    med = f.groupby("width_px")[col].median().reindex(w)
    # the seed band: what one fit scatters by with everything else held fixed
    sd = seed.groupby(["sensor", "width_px"])[col].std(ddof=1).median()
    X = list(range(len(w)))
    ax.fill_between(X, med - sd, med + sd, color="#4c72b0", alpha=.18, zorder=2,
                    label=f"seed-to-seed sd of one fit (±{sd:.3f} N)")
    ax.plot(X, med, "o-", color="#4c72b0", lw=2.2, ms=7, zorder=4,
            label="median of 17 units")
    ax.axhline(np.median(list(floor.values())), color="#c44e52", ls="--", lw=1.6,
               zorder=3, label=f"label noise floor ({np.median(list(floor.values())):.3f} N)")
    ax.axhline(scalar, color="#55a868", ls=":", lw=1.8, zorder=3,
               label=f"two scalars per frame ({scalar:.3f} N)")
    ax.axhline(1 / 16, color="0.4", ls="-.", lw=1.2, zorder=3,
               label=f"ATI Mini45 quoted {'Fz' if name == 'Fz' else 'Fxy'} resolution "
                     f"({'1/16' if name == 'Fz' else '1/32'} N)")
    # y is LINEAR (operator, 2026-09-08). A log y flattens the one thing this
    # figure is for -- how much worse 8x5 is than everything above it -- into a
    # step that looks like the wobble between neighbouring sizes.
    ax.set_xticks(X)
    hgt = {int(a): int(b) for a, b in zip(f.width_px, f.height_px)}
    ax.set_xticklabels([f"{a}×{hgt[a]}" for a in w], rotation=45, ha="right", fontsize=8)
    ax.set_xlim(-0.4, len(w) - 0.6)
    ax.set_ylim(0, None)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=8, steps=[1, 2, 2.5, 5, 10]))
    ax.minorticks_off()
    ax.set_xlabel("input size the network sees")
    ax.set_ylabel(f"{name} MAE (N), held-out cycles")
    _sub = ("flat from 1920×1080 down to 16×9, and breaks at 8×5" if col == "fz_mae"
            else "is a U: best near 80×45, worse at both ends")
    ax.set_title(f"{name} estimation {_sub}\n"
                 "17 units, one fit per cell; the band is what a re-run with a different seed moves by",
                 fontsize=10)
    ax.grid(alpha=.25, lw=.6)
    ax.legend(fontsize=8, framealpha=.9)
    fig.tight_layout()
    fig.savefig(FIGS / out, dpi=140)
    plt.close(fig)
    print(f"  -> {(FIGS/out).relative_to(ROOT)}")


def fig_per_unit(f, seed, floor, scalar, col="fz_mae", name="Fz", out="force_vs_resolution_units.png"):
    """One panel per unit, laid out as the 3x3 design plus replicate.

    The point of the small multiples is not to find each unit's best size --
    that is what the seed study says cannot be read off one fit. It is to show
    that every unit's curve wanders inside the same band, so the wandering is
    the fit's noise and not seventeen different resolution requirements.
    """
    sd = seed.groupby(["sensor", "width_px"])[col].std(ddof=1).median()
    order = [f"{h}_{t}mm_{r}" for t in THICK for r in ("r1", "r2") for h in HARDS]
    w = sorted(f.width_px.unique())
    xi = {v: i for i, v in enumerate(w)}      # categorical x, as in fig_resolution
    X = list(range(len(w)))
    hgt = {int(a): int(b) for a, b in zip(f.width_px, f.height_px)}
    fig, axes = plt.subplots(6, 3, figsize=(11.5, 13.5), sharex=True, sharey=True)
    for ax, s in zip(axes.ravel(), order):
        g = f[f.sensor == s].sort_values("width_px")
        if not len(g):
            ax.axis("off")
            continue
        med = g[col].median()
        ax.axhspan(med - sd, med + sd, color="#4c72b0", alpha=.13, zorder=1,
                   label="median ± seed sd")
        ax.axhline(med, color="#4c72b0", lw=1.1, ls="-", alpha=.55, zorder=2)
        ax.axhline(floor[s], color="#c44e52", ls="--", lw=1.3, zorder=3,
                   label="label noise floor")
        ax.axhline(scalar[s], color="#55a868", ls=":", lw=1.5, zorder=3,
                   label="two scalars")
        ax.plot([xi[v] for v in g.width_px], g[col], "o-", color="#22303f",
                lw=1.5, ms=4.5, zorder=5)
        ax.set_title(f"{s}   median {med:.3f} N", fontsize=9.5, pad=4)
        ax.grid(alpha=.22, lw=.5)
    for ax in axes.ravel():
        ax.set_xticks(X)               # categorical x, linear y -- see above
        ax.set_xlim(-0.4, len(w) - 0.6)
        ax.set_ylim(0, None)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
        ax.minorticks_off()
    for ax in axes[-1]:
        ax.set_xticklabels([f"{a}×{hgt[a]}" for a in w], rotation=90, fontsize=7)
    for r in range(6):
        axes[r][0].set_ylabel(f"{name} MAE (N)", fontsize=9)
    h, lb = axes[0][0].get_legend_handles_labels()
    fig.legend(h, lb, loc="upper center", ncol=3, fontsize=9, frameon=False,
               bbox_to_anchor=(0.5, 0.972))
    fig.suptitle(f"{name} estimation error against input size, one panel per unit\n"
                 "columns: soft / medium / hard   ·   rows: 1 mm r1, r2, 2 mm r1, r2, "
                 "3 mm r1, r2   ·   shared axes, linear y",
                 fontsize=11.5, y=0.995)
    fig.supxlabel("input size the network sees", fontsize=10)
    fig.tight_layout(rect=(0, 0.012, 1, 0.955))
    fig.savefig(FIGS / out, dpi=140)
    plt.close(fig)
    print(f"  -> {(FIGS/out).relative_to(ROOT)}")


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
    # v2: one batch for every resolution, a validation split choosing the
    # epoch, and both held-out definitions. The v1 table it replaces had a
    # batch that shrank with the picture and no validation set at all.
    src = DATA / "force_vs_resolution_v2.csv"
    f = pd.read_csv(src if src.exists() else DATA / "force_vs_resolution.csv")
    if "split" in f.columns:
        f = f[f.split == "cycle"].copy()      # the honest split; random is §2.5
    # v2 seed study: the same recipe as the v2 sweep (one batch, a validation
    # split choosing the epoch). The v1 numbers cannot be mixed with the v2
    # sweep -- they were measured under an optimiser that changed with the
    # picture, and they are 3x noisier for it (Fz sd 0.0219 against 0.0072).
    _sv2 = DATA / "force_seed_study_v2.csv"
    seed = pd.read_csv(_sv2 if _sv2.exists() else DATA / "force_seed_study.csv")
    sc = pd.read_csv(DATA / "force_scalar_baseline.csv")
    floor = label_noise("fz")
    floor_lat = label_noise("lat")
    per = f.groupby("sensor").agg(fz=("fz_mae", "median"), lat=("lat_mae", "median"),
                                  r2=("fz_r2", "median"), sd=("fz_mae", "std"),
                                  n=("fz_mae", "size"))
    per["se"] = per.sd / np.sqrt(per.n)
    FIGS.mkdir(parents=True, exist_ok=True)
    fig_resolution(f, seed, floor, float(sc.fz_mae.median()))
    fig_per_unit(f, seed, floor, sc.set_index("sensor").fz_mae.to_dict())
    fig_resolution(f, seed, floor_lat, float(sc.lat_mae.median()),
                   col="lat_mae", name="shear |Fxy|", out="shear_vs_resolution.png")
    fig_per_unit(f, seed, floor_lat, sc.set_index("sensor").lat_mae.to_dict(),
                 col="lat_mae", name="shear |Fxy|", out="shear_vs_resolution_units.png")
    fig_grid(per)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
