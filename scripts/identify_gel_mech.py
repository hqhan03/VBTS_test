#!/usr/bin/env python3
"""Which gel was really mounted? Match the force-depth curve, not the label.

Gel names are typed by hand and can be wrong. The gel's own load curve is a
better fingerprint than its picture: an attempt to identify units from the
resting image's texture managed only 15 of 18 on its own self-test, while the
ladder's force at a given indentation separates units cleanly -- two runs of the
same gel with different probes agreed to 0.015 N, and its neighbours in the same
cell were 0.09-0.19 N away.

The zero differs between runs (the force fit and the image onset disagree by
0.12-0.70 mm depending on the unit), which shifts the curve along depth, so the
match is taken over a free depth offset and the offset is reported: a physically
plausible one is |offset| < 0.3 mm.

  identify_gel_mech.py <dataset to check> <reference dataset>

Both must hold `shape_<probe>/ladder.csv` per run.
"""
import sys, re
import numpy as np, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def curves(ds):
    probe = ds.split("_")[-1]
    out = {}
    for run in sorted((ROOT / "data" / "20260911_VBTSresolution_dataset" / "DIGIT" / ds).glob("DIGIT_*")):
        f = run / f"shape_{probe}" / "ladder.csv"
        if not f.exists():
            continue
        L = pd.read_csv(f).sort_values("depth_mm")
        if len(L) >= 4:
            out[re.sub(r"__\d+$", "", run.name).replace("DIGIT_", "")] = (
                L.depth_mm.values, L.force_N.values)
    return out


def rms_with_shift(q, r, shifts=np.arange(-0.35, 0.351, 0.01)):
    """Best RMS between query and reference over a free depth offset."""
    qd, qf = q
    rd, rf = r
    best = (np.inf, 0.0)
    for s in shifts:
        d = qd + s
        m = (d >= rd.min()) & (d <= rd.max())
        if m.sum() < 3:
            continue
        e = float(np.sqrt(np.mean((qf[m] - np.interp(d[m], rd, rf)) ** 2)))
        if e < best[0]:
            best = (e, float(s))
    return best


if __name__ == "__main__":
    check, refds = sys.argv[1], sys.argv[2]
    Q, R = curves(check), curves(refds)
    print(f"  {check}: {len(Q)} 런   기준 {refds}: {len(R)} 런\n")
    rows = []
    for u, q in sorted(Q.items()):
        sc = {v: rms_with_shift(q, r) for v, r in R.items()}
        order = sorted(sc, key=lambda k: sc[k][0])
        best, second = order[0], order[1]
        claimed = sc.get(u, (np.inf, 0))
        rows.append(dict(run=u, best=best, best_rms=round(sc[best][0], 4),
                         best_shift=round(sc[best][1], 3),
                         claimed_rms=round(claimed[0], 4),
                         second=second, second_rms=round(sc[second][0], 4),
                         agrees=best == u))
        flag = "OK " if best == u else "!! "
        print(f"  {flag}{u:16s} 최적 {best:16s} rms {sc[best][0]:.4f} (이동 {sc[best][1]:+.2f} mm)"
              f"   라벨 {claimed[0]:.4f}   2위 {second:16s} {sc[second][0]:.4f}")
    df = pd.DataFrame(rows)
    out = ROOT / "data" / f"gel_identity_mech_{check.split('_')[-1]}.csv"
    df.to_csv(out, index=False)
    print(f"\n  라벨과 일치 {df.agrees.sum()}/{len(df)}  ->", out)
