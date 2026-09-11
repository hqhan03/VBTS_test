#!/usr/bin/env python3
"""Every unit, every cylinder pair: the table behind docs/spatial_resolution.md.

`analyse_resolution.py` judges one sensor against one probe and prints it.
This walks all seventeen units and all four pairs through exactly that code and
writes `data/20260911_VBTSresolution_dataset/9DTact/resolution_measurements.csv`, so the table can be rebuilt
whenever anything upstream of it changes -- as it did on 2026-09-08, when the
scale phase learned to notice a collapsed correlation and every unit gained a
trusted scale of its own, which is the mm axis this whole analysis is measured
on. It was an inline loop before, which is why it could not simply be re-run.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import analyse_resolution as A  # noqa: E402

UNITS = [f"9DTact_{h}_{t}mm_r{i}"
         for h in ("soft", "medium", "hard") for t in (1, 2, 3) for i in (1, 2)
         if not (h == "medium" and t == 2 and i == 1)]
PROBES = ["pair100", "pair075", "pair050", "pair025"]


def rows_for(sensor, probe, gaps):
    ds = ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact" / f"20260905_passA_{probe}"
    reject = A.SET_ASIDE + A.WRONG_UNIT
    cands = []
    for c in ds.glob(f"{sensor}*"):
        if not c.is_dir() or any(r in c.name for r in reject):
            continue
        base = A._RERUN.sub("", c.name)
        if base == sensor and (c / f"shape_{probe}" / "ladder.csv").exists():
            cands.append(c)
    if not cands:
        return []
    run = max(cands, key=lambda c: c.stat().st_mtime)
    st = json.loads((run / "state.json").read_text())
    J = A.jacobian(st, sensor)
    if J is None:
        print(f"  {sensor} {probe}: no scale")
        return []
    d = run / f"shape_{probe}"
    sep = A.ELEMENT_MM + gaps[probe]
    ref = cv2.cvtColor(cv2.imread(str(run / "reference.png")), cv2.COLOR_BGR2GRAY)
    lad = pd.read_csv(d / "ladder.csv")
    short = sensor.replace("9DTact_", "")
    hard, th = short.split("_")[0], int(short.split("_")[1][0])
    out = []
    for dep, grp in lad.groupby(lad.target_depth_mm):
        dips = []
        for _, row in grp.iterrows():
            img = cv2.cvtColor(cv2.imread(str(d / row.file)), cv2.COLOR_BGR2GRAY)
            raw = np.clip(ref.astype(np.int32) - img.astype(np.int32),
                          0, 255).astype(np.uint8)
            c = A.blob_centre(raw)
            if c is None:
                continue
            dw, ppm = A.isotropic(raw.astype(np.float32), J, c)
            got = A.axis_and_profile(dw, ppm)
            if got is None:
                continue
            x, prof, _ = got
            f, peak, sd1, m, sy = A.dip_fraction(x, prof, sep)
            if np.isfinite(f):
                dips.append((f, peak, sd1, m, sy))
        if not dips:
            continue
        fs = np.array([q[0] for q in dips])
        pk = float(np.mean([q[1] for q in dips]))
        own = np.nanmean([q[2] for q in dips])
        across = fs.std(ddof=1) / np.sqrt(len(fs)) if len(fs) > 1 else np.nan
        sd = float(np.nanmax([own, across])) if (np.isfinite(own) or np.isfinite(across)) else np.nan
        weak = not np.isfinite(pk) or pk < A.MIN_PEAK
        ok = bool(not weak and fs.mean() >= A.RAYLEIGH and np.isfinite(sd)
                  and fs.mean() > A.NOISE_K * sd)
        out.append(dict(gap=sep, sensor=short, th=th, hard=hard, depth=float(dep),
                        dip=float(fs.mean()), sd=sd, peak=pk,
                        sym=float(np.nanmean([q[4] for q in dips])),
                        mtf=float(np.nanmean([q[3] for q in dips])), ok=ok))
    return out


def main() -> int:
    gaps = {p["id"]: p["gap_mm"]
            for p in yaml.safe_load(open(ROOT / "config" / "probes.yaml"))["probes"]
            if p["tip"] == "cylinder_pair"}
    rows = []
    for sensor in UNITS:
        got = []
        for probe in PROBES:
            got += rows_for(sensor, probe, gaps)
        rows += got
        n = sum(1 for r in got if r["ok"])
        print(f"{sensor:24} {len(got):3d} rungs, {n:2d} resolved")
    df = pd.DataFrame(rows)
    out = ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact" / "resolution_measurements.csv"
    df.to_csv(out, index=False)
    print(f"\n{len(df)} rows -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
