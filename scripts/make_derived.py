#!/usr/bin/env python3
"""The contact-radius table, the correlation table, and the figures.

`docs/contact_variable.md` asks whether one variable -- the radius of the
circle that changes brightness -- can stand in for gel thickness and hardness
together, and `spatial_resolution.md` and `shape_reconstruction.md` show the
3x3 grid of the two variables against every score. All of that was built by
loops typed into a shell, so when the image scale changed on 2026-09-08 (every
unit gained a trusted scale of its own; five had been on the median of the
others) there was nothing to re-run. This is that code, written down.

The radius depends on the scale directly -- it is a pixel count turned into
millimetres -- so it is recomputed from the ladder frames here rather than
carried over.

    scripts/make_derived.py            # CSV + figures
    scripts/make_derived.py --no-figs  # CSV and the correlation table only
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "9DTact"
FIGS = ROOT / "docs" / "figures"
DIFF_LEVEL = 7          # grey levels above the reference that count as contact
HARDS = ["soft", "medium", "hard"]
THICK = [1, 2, 3]


def ladder_radii(sensor: str):
    """Radius in pixels, depth, force and mean darkening down the ball4 ladder."""
    ds = DATA / "20260905_passA_ball4"
    cands = [c for c in ds.glob(f"9DTact_{sensor}*")
             if c.is_dir() and (c / "shape_ball4" / "ladder.csv").exists()
             and c.name.split("__")[0] == f"9DTact_{sensor}"]
    if not cands:
        return None
    run = max(cands, key=lambda c: c.stat().st_mtime)
    ref = cv2.cvtColor(cv2.imread(str(run / "reference.png")), cv2.COLOR_BGR2GRAY)
    lad = pd.read_csv(run / "shape_ball4" / "ladder.csv")
    out = []
    for _, r in lad.iterrows():
        img = cv2.cvtColor(cv2.imread(str(run / "shape_ball4" / r.file)),
                           cv2.COLOR_BGR2GRAY)
        d = np.clip(ref.astype(np.int32) - img.astype(np.int32), 0, 255)
        m = d >= DIFF_LEVEL
        n = int(m.sum())
        out.append(dict(depth=float(r.depth_mm), force=float(abs(r.force_N)),
                        radius_px=float(np.sqrt(n / np.pi)) if n else np.nan,
                        level=float(d[m].mean()) if n else np.nan))
    return pd.DataFrame(out).sort_values("depth")


def interp(x, y, at):
    """y where x = at, linear, only inside the measured range."""
    g = np.isfinite(x) & np.isfinite(y)
    x, y = np.asarray(x)[g], np.asarray(y)[g]
    if len(x) < 2 or at < x.min() or at > x.max():
        return np.nan
    o = np.argsort(x)
    return float(np.interp(at, x[o], y[o]))


def build():
    res = pd.read_csv(DATA / "resolution_measurements.csv")
    shp = pd.read_csv(DATA / "shape_reconstruction.csv").set_index("sensor")
    reg = yaml.safe_load(open(ROOT / "config" / "sensor_registry.yaml"))
    hertz = {e["id"].replace("9DTact_", ""): (e.get("gel_model") or {}).get("hertz_a")
             for e in reg["sensors"]}
    rows = []
    for sensor in shp.index:
        lad = ladder_radii(sensor)
        s = shp.loc[sensor]
        ppm = float(s.px_per_mm)
        rsub = res[res.sensor == sensor]
        rec = dict(sensor=sensor, hard=sensor.split("_")[0],
                   th=int(sensor.split("_")[1][0]), ppm=ppm,
                   # gaps resolved (0-4), not rungs: a gap counts once however
                   # many depths of the ladder resolved it.
                   n_resolved=int(rsub[rsub.ok].gap.nunique()),
                   dip_175_max=float(rsub[np.isclose(rsub.gap, 1.75)].dip.max())
                   if (np.isclose(rsub.gap, 1.75)).any() else np.nan,
                   dip_200_max=float(rsub[np.isclose(rsub.gap, 2.00)].dip.max())
                   if (np.isclose(rsub.gap, 2.00)).any() else np.nan,
                   mtf_200_max=float(rsub[np.isclose(rsub.gap, 2.00)].mtf.max())
                   if (np.isclose(rsub.gap, 2.00)).any() else np.nan,
                   scale_source=s.scale_source,
                   mm_per_grey_level=float(s.mm_per_grey_level),
                   um_per_level=1000 * float(s.mm_per_grey_level),
                   cyl4_corrected_rms_after_linear=float(s.cyl4_corrected_rms_after_linear),
                   cyl4_corrected_bias_deep=float(s.cyl4_corrected_bias_deep),
                   hertz_a=hertz.get(sensor))
        if lad is not None:
            r_mm = lad.radius_px / ppm
            rec.update(Fmax_ladder=float(lad.force.max()),
                       r_img_d05=interp(lad.depth, r_mm, 0.5),
                       r_img_F05=interp(lad.force, r_mm, 0.5),
                       r_img_F02=interp(lad.force, r_mm, 0.2),
                       depth_at_F05=interp(lad.force, lad.depth, 0.5))
            g = np.isfinite(lad.level)
            rec["img_slope_lvl_per_mm"] = (float(np.polyfit(lad.depth[g], lad.level[g], 1)[0])
                                           if g.sum() >= 3 else np.nan)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_csv(DATA / "contact_radius.csv", index=False)
    return df


CANDIDATES = [("r_img_d05", "반지름 @ 0.5 mm"), ("r_img_F02", "반지름 @ 0.2 N"),
              ("hertz_a", "접촉 강성 a"), ("img_slope_lvl_per_mm", "이미지 감도")]
SCORES = [("n_resolved", "분해 간격 수"), ("dip_175_max", "dip @ 1.75 mm"),
          ("um_per_level", "µm / 단계"),
          ("cyl4_corrected_rms_after_linear", "형상 RMS")]


def correlations(df):
    def cell(a, b):
        g = df[[a, b]].dropna()
        if len(g) < 4:
            return f"n={len(g)}"
        r, p = spearmanr(g[a], g[b])
        return f"{r:+.2f} ({p:.2f}, n={len(g)})"
    print("\n| 변수 | " + " | ".join(n for _, n in SCORES) + " |")
    print("|---|" + "---|" * len(SCORES))
    for c, name in CANDIDATES:
        print(f"| {name} | " + " | ".join(cell(c, s) for s, _ in SCORES) + " |")
    print("\n| 변수 | 두께와의 상관 | 경도와의 상관 |")
    print("|---|---|---|")
    hn = {"soft": 0, "medium": 1, "hard": 2}
    d = df.assign(_h=df.hard.map(hn))
    for c, name in CANDIDATES:
        g = d[[c, "th", "_h"]].dropna()
        rt, pt = spearmanr(g[c], g.th)
        rh, ph = spearmanr(g[c], g._h)
        print(f"| {name} | {rt:+.2f} ({pt:.2f}, n={len(g)}) | {rh:+.2f} ({ph:.2f}, n={len(g)}) |")


def bar3d(df, col, title, zlabel, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    fig = plt.figure(figsize=(7.5, 5.5))
    ax = fig.add_subplot(111, projection="3d")
    cmap = plt.get_cmap("viridis")
    v = df[col].astype(float)
    lo, hi = np.nanmin(v), np.nanmax(v)
    for _, r in df.iterrows():
        if not np.isfinite(r[col]):
            continue
        xi = HARDS.index(r.hard)
        yi = THICK.index(int(r.th))
        rep = 0 if r.sensor.endswith("r1") else 1      # r1 left, r2 right
        c = cmap(0.15 + 0.75 * (r[col] - lo) / (hi - lo + 1e-12))
        ax.bar3d(xi - 0.34 + 0.36 * rep, yi - 0.18, 0, 0.30, 0.36,
                 float(r[col]), color=c, edgecolor="0.25", linewidth=0.4,
                 shade=True)
    ax.set_xticks(range(3)); ax.set_xticklabels(HARDS)
    ax.set_yticks(range(3)); ax.set_yticklabels([f"{t} mm" for t in THICK])
    ax.set_xlabel("hardness"); ax.set_ylabel("gel thickness")
    ax.set_zlabel(zlabel)
    ax.set_title(f"{title}\n(each cell: r1 left, r2 right)", fontsize=10)
    ax.view_init(elev=22, azim=-58)
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)
    print(f"  -> {path.relative_to(ROOT)}")


def scatter_grid(df, col, name, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.3))
    mk = {"soft": "o", "medium": "s", "hard": "^"}
    cl = {1: "#4c72b0", 2: "#dd8452", 3: "#55a868"}
    for ax, (s, sname) in zip(axes, SCORES):
        g = df[[col, s, "hard", "th"]].dropna()
        for _, r in g.iterrows():
            ax.scatter(r[col], r[s], marker=mk[r.hard], c=cl[int(r.th)],
                       s=46, edgecolor="0.2", linewidth=0.5)
        if len(g) >= 4:
            rr, pp = spearmanr(g[col], g[s])
            ax.set_title(f"{sname}\nrho {rr:+.2f}, p {pp:.2f}, n={len(g)}", fontsize=9)
        ax.set_xlabel(name, fontsize=9)
        ax.grid(alpha=.25, linewidth=.6)
    h = ([plt.Line2D([], [], marker=mk[k], ls="", c="0.35", label=k) for k in mk]
         + [plt.Line2D([], [], marker="o", ls="", c=cl[k], label=f"{k} mm") for k in cl])
    fig.legend(handles=h, loc="upper right", ncol=6, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=140); plt.close(fig)
    print(f"  -> {path.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-figs", action="store_true")
    a = ap.parse_args()
    df = build()
    print(df[["sensor", "scale_source", "ppm", "r_img_d05", "r_img_F02",
              "n_resolved", "um_per_level"]].to_string(index=False,
                                                       float_format=lambda v: f"{v:8.3f}"))
    correlations(df)
    if a.no_figs:
        return 0
    FIGS.mkdir(parents=True, exist_ok=True)
    print()
    bar3d(df, "n_resolved", "Spatial resolution: gaps resolved (of 4)",
          "gaps resolved", FIGS / "res3d_nresolved.png")
    bar3d(df, "dip_175_max", "Spatial resolution: best dip at a 1.75 mm gap",
          "dip", FIGS / "res3d_dip175.png")
    bar3d(df, "um_per_level", "Shape: depth resolution",
          "um per grey level", FIGS / "shape3d_um.png")
    bar3d(df, "cyl4_corrected_rms_after_linear",
          "Shape: residual after a linear correction", "rms (mm)",
          FIGS / "shape3d_rms.png")
    for col, name, fn in (("r_img_d05", "contact radius at 0.5 mm (mm)", "radius_d05_vs_metrics.png"),
                          ("r_img_F02", "contact radius at 0.2 N (mm)", "radius_F02_vs_metrics.png"),
                          ("hertz_a", "contact stiffness a (N/mm^1.5)", "hertz_a_vs_metrics.png"),
                          ("img_slope_lvl_per_mm", "image sensitivity (levels/mm)", "imgslope_vs_metrics.png")):
        scatter_grid(df, col, name, FIGS / fn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
