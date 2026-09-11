#!/usr/bin/env python3
"""What the flat-punch ladder measured, per unit.

cyl4 is a 4 mm flat cylinder. Unlike a sphere its contact area does not grow
with depth, so the force it takes to reach a depth reads the gel's stiffness
with no Hertz geometry in the way, and the imprint it leaves is a disc of KNOWN
diameter -- a ruler for the image scale as well as a shape target.

Per unit, from data/<principle>/20260910_passA_cyl4/*/shape_cyl4/ladder.csv:

  k_N_per_mm       slope of force against REACHED depth: the punch stiffness
  F_at_0.1mm       force at 0.1 mm of indentation (interpolated)
  d_at_1N          depth at 1 N (interpolated)
  n_rungs          rungs that survived the force guard (deeper ones are skipped
                   once a rung passes 70 % of the ceiling, so a stiff gel keeps
                   fewer -- this is a property of the gel, not a defect)
  r_disc_px        imprint radius at the deepest rung
  px_per_mm_disc   r_disc_px / 2 mm, an independent scale estimate, valid only
                   once the gel has closed around the punch

Writes data/analysis/cyl4_summary.csv.
"""
import re
import numpy as np, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DS = "20260910_passA_cyl4"
PUNCH_R_MM = 2.0


def interp(x, y, at):
    o = np.argsort(x)
    x, y = np.asarray(x)[o], np.asarray(y)[o]
    return float(np.interp(at, x, y)) if x.min() <= at <= x.max() else np.nan


def rows_for(principle):
    base = ROOT / "data" / "20260911_VBTSresolution_dataset" / principle / DS
    out = []
    if not base.exists():
        return out
    for run in sorted(base.glob(f"{principle}_*")):
        lad = run / "shape_cyl4" / "ladder.csv"
        if not lad.exists():
            continue
        L = pd.read_csv(lad).sort_values("depth_mm")
        if len(L) < 3:
            print(f"  {run.name}: {len(L)} 단뿐 — 건너뜀"); continue
        unit = re.sub(r"__\d+$", "", run.name).replace(principle + "_", "")
        m = re.search(r"(soft|medium|hard)_(\d)mm_r(\d)", unit)
        if not m:
            continue
        k = float(np.polyfit(L.depth_mm, L.force_N, 1)[0])
        r_disc = float(L.radius_px.iloc[-1])
        out.append(dict(
            principle=principle, unit=unit, run=run.name, hardness=m.group(1),
            thickness_mm=int(m.group(2)), rep=int(m.group(3)), n_rungs=len(L),
            k_N_per_mm=round(k, 2),
            F_at_0p1mm=round(interp(L.depth_mm, L.force_N, 0.1), 4),
            d_at_1N=round(interp(L.force_N, L.depth_mm, 1.0), 4),
            area_slope_px_per_mm=round(float(np.polyfit(L.depth_mm, L.area_px, 1)[0]), 0),
            r_disc_px=round(r_disc, 1),
            px_per_mm_disc=round(r_disc / PUNCH_R_MM, 1),
            depth_max_mm=round(float(L.depth_mm.max()), 3),
            force_max_N=round(float(L.force_N.max()), 3)))
    return out


if __name__ == "__main__":
    rows = []
    for p in ("DIGIT", "DIGIT_Marker", "9DTact"):
        r = rows_for(p)
        print(f"  {p}: {len(r)} 유닛")
        rows += r
    d = pd.DataFrame(rows)
    out = ROOT / "data" / "analysis" / "cyl4_summary.csv"
    d.to_csv(out, index=False)
    print("  ->", out, len(d), "rows")
