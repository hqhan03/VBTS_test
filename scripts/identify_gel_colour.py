#!/usr/bin/env python3
"""Which gel was really mounted? Match the resting colour ratio.

Gel names are typed by hand. Two other fingerprints failed: the reference
image's high-pass texture (15 of 18 on its own self-test, margins near zero) and
the force-depth curve (perfect within one probe, useless across probes, because
changing the probe changes the load curve more than changing the gel does).

What does survive both a remount and a probe change is the gel's COLOUR. DIGIT
lights the gel from the side with R/G/B LEDs, and how much of each colour comes
back depends on the silicone's own scattering and absorption, not on how bright
the frame is. So take the channel means of the resting frame, divide by their
sum -- which removes brightness, the part that changes with the probe's shadow
and the standoff -- and match the 3-vector against a library.

On the pair025 pass against the Pass B library this gets 17 of 19, and where it
agrees the claimed unit is 5-20x closer than the runner-up, so a disagreement
with a margin that size is evidence about the gel, not noise.

  identify_gel_colour.py <dataset> [dataset ...]
"""
import sys, re, yaml
import numpy as np, cv2, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "data" / "DIGIT" / "20260908_passB_ball8"


def ratio(path):
    im = cv2.imread(str(path))
    if im is None:
        return None
    v = np.array([float(im[:, :, i].mean()) for i in range(3)])
    s = v.sum()
    return v / s if s > 0 else None


def library():
    can = yaml.safe_load((LIB / "CANONICAL.yaml").read_text())["canonical"]
    out = {}
    for u, v in can.items():
        r = ratio(LIB / v["run"] / "reference_collect.png")
        if r is not None:
            out[u.replace("DIGIT_", "")] = r
    return out


if __name__ == "__main__":
    lib = library()
    rows = []
    for ds in sys.argv[1:]:
        base = ROOT / "data" / "DIGIT" / ds
        if not base.exists():
            print(f"  {ds}: 없음"); continue
        print(f"\n=== {ds} ===")
        for run in sorted(base.glob("DIGIT_*")):
            f = run / "reference_working.png"
            if not f.exists():
                f = run / "reference.png"
            q = ratio(f)
            if q is None:
                continue
            claimed = re.sub(r"__\d+$", "", run.name).replace("DIGIT_", "")
            d = {u: float(np.linalg.norm(q - v)) for u, v in lib.items()}
            o = sorted(d, key=d.get)
            best, second = o[0], o[1]
            rows.append(dict(dataset=ds, run=run.name, claimed=claimed, best=best,
                             best_d=round(d[best], 4), claimed_d=round(d.get(claimed, np.nan), 4),
                             second=second, second_d=round(d[second], 4),
                             margin=round(d[second] / max(d[best], 1e-9), 1),
                             agrees=best == claimed, source=f.name))
            print(f"  {'OK ' if best == claimed else '!! '}{claimed:16s} -> {best:16s} "
                  f"d {d[best]:.4f}  (라벨 {d.get(claimed, np.nan):.4f}, 2위 {d[second]:.4f}, "
                  f"여유 {d[second]/max(d[best],1e-9):.1f}x)")
    df = pd.DataFrame(rows)
    out = ROOT / "data" / "gel_identity_colour.csv"
    df.to_csv(out, index=False)
    print(f"\n  일치 {df.agrees.sum()}/{len(df)}  ->", out)
