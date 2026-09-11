#!/usr/bin/env python3
"""The same-force contact radius, from the ball8 ramp, for all seventeen units.

`contact_variable.md` tests two definitions of "the radius of the circle whose
brightness changed". The same-DEPTH one comes from the ball4 ladder. The
same-FORCE one could not: ball4 reached only 0.1-0.8 N on the softer units, so
the reading at 0.5 N existed for six of seventeen and had to be dropped to
0.2 N, where the imprint is barely formed.

Pass B's characterize ramp presses ball8 to about 2.9 N in 0.1 mm steps and
records `radius_px` at every step, so the radius can be read at a force where
the imprint is fully developed, on every unit. The ball8 tip is wider than
ball4, so these radii are not comparable with the ball4 ones -- only with each
other.

    scripts/contact_radius_ball8.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact"
PASSB = DATA / "20260907_passB_ball8"
FORCES = (0.5, 1.0, 2.0)


def interp(x, y, at):
    g = np.isfinite(x) & np.isfinite(y)
    x, y = np.asarray(x)[g], np.asarray(y)[g]
    if len(x) < 2 or at < x.min() or at > x.max():
        return np.nan
    o = np.argsort(x)
    return float(np.interp(at, x[o], y[o]))


def main() -> int:
    scale = pd.read_csv(DATA / "shape_reconstruction.csv").set_index("sensor")
    cr = pd.read_csv(DATA / "contact_radius.csv").set_index("sensor")
    rows = []
    for d in sorted(PASSB.iterdir()):
        f = d / "characterize" / "steps.csv"
        if not f.exists():
            continue
        s = d.name.replace("9DTact_", "")
        if s not in scale.index:
            continue
        st = pd.read_csv(f)
        ppm = float(scale.loc[s, "px_per_mm"])
        r_mm = st.radius_px / ppm
        rec = dict(sensor=s, th=int(s.split("_")[1][0]), hard=s.split("_")[0],
                   ppm=ppm, Fmax=float(st.force_N.max()))
        for F in FORCES:
            rec[f"r_ball8_{F}N"] = interp(st.force_N, r_mm, F)
        for c in ("n_resolved", "dip_175_max", "um_per_level",
                  "cyl4_corrected_rms_after_linear", "fz_mae"):
            rec[c] = float(cr.loc[s, c]) if c in cr.columns else np.nan
        rows.append(rec)
    df = pd.DataFrame(rows)
    out = DATA / "contact_radius_ball8.csv"
    df.to_csv(out, index=False)
    cols = ["sensor", "th", "hard", "Fmax"] + [f"r_ball8_{F}N" for F in FORCES]
    print(df[cols].to_string(index=False, float_format=lambda v: f"{v:7.3f}"))
    print(f"\n{len(df)} units -> {out}")

    from scipy.stats import spearmanr
    hn = {"soft": 0, "medium": 1, "hard": 2}
    print("\n| 변수 | 두께와의 상관 | 경도와의 상관 |\n|---|---|---|")
    for F in FORCES:
        g = df[[f"r_ball8_{F}N", "th", "hard"]].dropna()
        rt, pt = spearmanr(g[f"r_ball8_{F}N"], g.th)
        rh, ph = spearmanr(g[f"r_ball8_{F}N"], g.hard.map(hn))
        print(f"| 반지름 @ {F} N (ball8) | {rt:+.2f} ({pt:.2f}, n={len(g)}) | "
              f"{rh:+.2f} ({ph:.2f}, n={len(g)}) |")
    print("\n| 변수 | 분해 간격 수 | dip @ 1.75 mm | µm / 단계 | 형상 RMS | 힘 MAE |\n"
          "|---|---|---|---|---|---|")
    for F in FORCES:
        cells = []
        for c in ("n_resolved", "dip_175_max", "um_per_level",
                  "cyl4_corrected_rms_after_linear", "fz_mae"):
            g = df[[f"r_ball8_{F}N", c]].dropna()
            if len(g) < 4:
                cells.append(f"n={len(g)}")
                continue
            r, p = spearmanr(g[f"r_ball8_{F}N"], g[c])
            cells.append(f"{r:+.2f} ({p:.2f}, n={len(g)})")
        print(f"| 반지름 @ {F} N (ball8) | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
