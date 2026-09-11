#!/usr/bin/env python3
"""Two-point resolution per unit, compared at matched LOAD rather than depth.

The ladder is commanded in depth from each run's own fitted zero, but that zero
disagrees with the image onset by 0.12-0.70 mm depending on the unit, so "0.1 mm"
is not the same indentation on every unit -- comparing the dip at a fixed rung
mixes the sensor's resolution with how far the probe actually went in. Two
replicates of one cell came out 0.068 and 0.440 that way.

So interpolate each unit's dip against the measured NORMAL FORCE and against the
imprint AREA, and report it at common values of those. Force is what the F/T
measured, area is what the picture shows; neither depends on the zero.

  dip_at_<F>N     dip interpolated at that contact force
  dip_at_<A>kpx   dip interpolated at that imprint area
  F_rayleigh      force at which the dip first passes 0.265 (Rayleigh)
  F_d360          force at which it first passes 0.667 (Digit 360's MTF 0.5)

Usage: pair_summary.py <dataset> [dataset ...]
"""
import sys, re, subprocess
import numpy as np, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORCES = [0.2, 0.3, 0.5]
AREAS = [40, 60, 80]        # kilopixels


def dips_for(dataset, unit, probe):
    """Run the fixed criterion and read back its per-depth table."""
    out = subprocess.run(["/usr/bin/python3", str(ROOT / "scripts" / "analyse_resolution.py"),
                          dataset, unit, probe], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        m = re.match(r"\s+(\d\.\d\d)\s+(-?\d\.\d+)\s+(\d\.\d+)\s+(-?\d+\.\d+)\s+(\d\.\d+)", line)
        if m:
            rows.append(dict(depth=float(m.group(1)), dip=float(m.group(2)),
                             sd=float(m.group(3)), weak=float(m.group(4)),
                             sym=float(m.group(5))))
    return pd.DataFrame(rows)


def interp_at(x, y, xs):
    """y at each xs by linear interpolation; nan outside the measured range."""
    o = np.argsort(x)
    x, y = np.asarray(x)[o], np.asarray(y)[o]
    return [float(np.interp(v, x, y)) if x.min() <= v <= x.max() else np.nan for v in xs]


def first_cross(x, y, thr):
    """Smallest x where y first reaches thr, linearly interpolated."""
    o = np.argsort(x)
    x, y = np.asarray(x)[o], np.asarray(y)[o]
    for i in range(1, len(x)):
        if y[i] >= thr and y[i - 1] < thr:
            f = (thr - y[i - 1]) / max(y[i] - y[i - 1], 1e-9)
            return float(x[i - 1] + f * (x[i] - x[i - 1]))
    return float(x[0]) if len(y) and y[0] >= thr else np.nan


if __name__ == "__main__":
    datasets = sys.argv[1:] or ["20260909_passA_pair025", "20260909_passA_pair010"]
    rows = []
    for ds in datasets:
        probe = ds.split("_")[-1]
        base = ROOT / "data" / "20260911_VBTSresolution_dataset" / "DIGIT" / ds
        if not base.exists():
            print(f"  {ds}: 없음"); continue
        for run in sorted(base.glob("DIGIT_*")):
            unit = re.sub(r"__\d+$", "", run.name)
            lad = run / f"shape_{probe}" / "ladder.csv"
            if not lad.exists():
                continue
            L = pd.read_csv(lad)
            D = dips_for(ds, unit, probe)
            if D.empty:
                print(f"  {run.name}: dip 없음"); continue
            m = L.merge(D, left_on="target_depth_mm", right_on="depth", how="inner")
            if len(m) < 3:
                print(f"  {run.name}: 겹치는 단 {len(m)}"); continue
            g = re.search(r"(soft|medium|hard)_(\d)mm_r(\d)", unit)
            r = dict(unit=unit.replace("DIGIT_", ""), probe=probe, dataset=ds,
                     hardness=g.group(1), thickness_mm=int(g.group(2)), rep=int(g.group(3)),
                     n_rungs=len(m), dip_at_shallowest=float(m.dip.iloc[0]),
                     max_dip=float(m.dip.max()),
                     F_rayleigh=first_cross(m.force_N, m.dip, 0.265),
                     F_d360=first_cross(m.force_N, m.dip, 0.667),
                     A_rayleigh=first_cross(m.area_px, m.dip, 0.265) / 1000.0,
                     )
            for f, v in zip(FORCES, interp_at(m.force_N, m.dip, FORCES)):
                r[f"dip_at_{f}N"] = v
            for a, v in zip(AREAS, interp_at(m.area_px / 1000.0, m.dip, AREAS)):
                r[f"dip_at_{a}kpx"] = v
            rows.append(r)
            print(f"  {probe} {r['unit']:16s} dip@0.3N {r['dip_at_0.3N']:.3f}  "
                  f"dip@60kpx {r['dip_at_60kpx']:.3f}  F_Rayleigh {r['F_rayleigh']:.3f} N", flush=True)
    out = ROOT / "data" / "pair_resolution.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print("  ->", out, len(rows), "runs")
