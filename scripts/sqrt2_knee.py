#!/usr/bin/env python3
"""Does the saturation resolution depend on the gel? -- asked on a root-2 ladder.

The campaign's headline question was answered "yes" from a DOUBLING ladder,
where the shear knee correlated with thickness at rho -0.456 (p 0.057) on the
DIGIT grey sweep. Two rungs of that ladder are a factor of four apart, so a
knee that moves by one rung moves by 2x and nothing finer can be seen; and the
correlation did not survive changing the input representation
(`cross_principle.md` 3.10).

This reads the same knee off 16, 24, 32, 40, 48, 64, 80, 113, 160, 226, 320 px
-- root-2 spacing over the range where every unit's knee has ever been found --
with the same definition analyse_saturation.py uses: the smallest width whose
error is still within max(2 x seed sd, 15 % of best) of the unit's best.

`res_loss` is deliberately not reported. It is the error at the ladder's
SMALLEST rung minus the best, and this ladder starts at 16 px where the old one
started at 8, so the two are not comparable.
"""
import sys, re
import numpy as np, pandas as pd
from scipy.stats import spearmanr
HARD = {"soft": 0, "medium": 1, "hard": 2}


def knees(path, col):
    d = pd.read_csv(path)
    d["sh"] = d["lat_mae_shear"] if "lat_mae_shear" in d else d["lat_mae"]
    d["fz"] = d["fz_mae_normal"] if "fz_mae_normal" in d else d["fz_mae"]
    g = d.groupby(["sensor", "width_px"])[col].agg(["mean", "std"]).reset_index()
    rows = []
    for u, x in g.groupby("sensor"):
        x = x.sort_values("width_px")
        w, m = x.width_px.values, x["mean"].values
        sd = np.nan_to_num(x["std"].values, nan=0.0)
        ib = int(np.argmin(m)); best = m[ib]
        tol = max(2 * float(np.median(sd)), 0.15 * best)
        k = w[ib]
        for i in range(ib, -1, -1):
            if m[i] <= best + tol:
                k = w[i]
            else:
                break
        rows.append(dict(unit=u, th=int(re.search(r"_(\d)mm", u).group(1)),
                         hard=HARD[re.search(r"(soft|medium|hard)", u).group(1)],
                         knee=int(k), best=float(best)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    for pr in ("DIGIT", "DIGIT_Marker"):
        f = f"data/{pr}/force_vs_resolution_sqrt2.csv"
        try:
            for col, lab in (("sh", "shear"), ("fz", "Fz")):
                r = knees(f, col)
                st = spearmanr(r.th, r.knee); sh = spearmanr(r.hard, r.knee)
                print(f"{pr:13s} {lab:5s} n={len(r):2d}  "
                      f"knee by thickness {r.groupby('th').knee.median().to_dict()} "
                      f"rho {st.statistic:+.3f} p {st.pvalue:.3f}   "
                      f"by hardness {r.groupby('hard').knee.median().to_dict()} "
                      f"rho {sh.statistic:+.3f} p {sh.pvalue:.3f}")
        except FileNotFoundError:
            print(f"{pr}: {f} not written yet")
