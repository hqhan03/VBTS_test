#!/usr/bin/env python3
"""How much of the force does a single number from the image already carry?

`force_vs_resolution.py` found the ResNet's error to be flat from 1920x1080
down to 48x27, and still R2 0.94 at 8x5 -- forty pixels. Either the network is
reading spatial structure that survives to forty pixels, which is implausible,
or it is reading something a scalar carries. This measures the scalar.

For each frame the darker channel of the 9DTact representation is reduced to
two numbers: its mean over the frame, and the area above the same threshold the
ladders use. A ridge on [mean, area, sqrt(area), mean*sqrt(area)] is fitted on
the same training cycles the network saw and scored on the same held-out
cycles, so the comparison is like for like. Nothing is learned about where in
the image anything is.

    scripts/force_scalar_baseline.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import force_vs_resolution as F  # noqa: E402

OUT = ROOT / "data" / "9DTact" / "force_scalar_baseline.csv"


def features(X):
    d = X[:, :, :, 2].astype(np.float32)      # the darker channel, x3 already
    m = d.mean(axis=(1, 2))
    a = (d >= 21).mean(axis=(1, 2))           # 7 grey levels before REP_SCALE
    s = np.sqrt(a)
    return np.stack([m, a, s, m * s, np.ones_like(m)], axis=1)


def ridge(A, b, lam=1e-3):
    n = A.shape[1]
    return np.linalg.solve(A.T @ A + lam * n * np.eye(n), A.T @ b)


def main() -> int:
    rows = []
    runs = sorted(F.DATASET.glob("9DTact_*"))
    runs = [r for r in runs if (r / "stream" / "frames.csv").exists()]
    for run in runs:
        sensor = run.name.replace("9DTact_", "")
        X, y, cyc, blk = F.load_unit(run)
        tr, te = F.split_by_cycle(cyc, blk)
        A = features(X)
        rec = dict(sensor=sensor, n_train=int(tr.sum()), n_test=int(te.sum()))
        for j, ax in enumerate(("Fx", "Fy", "Fz")):
            w = ridge(A[tr], y[tr, j])
            p = A[te] @ w
            e = np.abs(p - y[te, j])
            rec[f"{ax.lower()}_mae"] = float(e.mean())
            if ax == "Fz":
                v = y[te, j]
                rec["fz_r2"] = float(1 - ((p - v) ** 2).sum() / ((v - v.mean()) ** 2).sum())
                rec["fz_mae_baseline"] = float(np.abs(v - y[tr, j].mean()).mean())
        rec["lat_mae"] = 0.5 * (rec["fx_mae"] + rec["fy_mae"])
        rows.append(rec)
        print(f"  {sensor:16} scalar Fz MAE {rec['fz_mae']:.4f} N  R2 {rec['fz_r2']:+.3f}  "
              f"lat {rec['lat_mae']:.4f}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"\n{len(df)} units -> {OUT}")
    print(f"median Fz MAE {df.fz_mae.median():.4f} N, R2 {df.fz_r2.median():.3f}, "
          f"lat {df.lat_mae.median():.4f} N")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
