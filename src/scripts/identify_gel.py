#!/usr/bin/env python3
"""Which physical gel was mounted? Ask the picture, not the label.

Gels are swapped by hand and named by whoever types the command, so a run's
folder name is a claim, not a measurement. Each gel does carry an identity in
its resting image: dust, casting texture and edge shape survive remounting,
while the illumination belongs to the body and is common to all of them. So
high-pass each reference (removes illumination, keeps texture), normalise, and
correlate against the Pass B reference of every unit.

Across the 18 DIGIT Pass B references the cross-unit correlation is 0.21-0.30,
so a match well above that band identifies the gel.

Usage: identify_gel.py <dataset> [dataset ...]
"""
import sys, re, yaml
import numpy as np, cv2, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "data" / "20260911_VBTSresolution_dataset" / "DIGIT" / "20260908_passB_ball8"


def sig(path):
    g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if g is None:
        return None
    g = g.astype(np.float32)
    hp = g - cv2.GaussianBlur(g, (0, 0), 15)
    hp = cv2.resize(hp, (480, 270))
    hp -= hp.mean()
    s = hp.std()
    return hp / s if s > 1e-6 else None


def library():
    can = yaml.safe_load((LIB / "CANONICAL.yaml").read_text())["canonical"]
    out = {}
    for u, v in can.items():
        p = LIB / v["run"] / "reference_collect.png"
        s = sig(p) if p.exists() else None
        if s is not None:
            out[u.replace("DIGIT_", "")] = s
    return out


if __name__ == "__main__":
    lib = library()
    rows = []
    for ds in sys.argv[1:]:
        base = ROOT / "data" / "20260911_VBTSresolution_dataset" / "DIGIT" / ds
        for run in sorted(base.glob("DIGIT_*")):
            claimed = re.sub(r"__\d+$", "", run.name).replace("DIGIT_", "")
            q = None
            for nm in ("reference_working.png", "reference.png", "touchcheck.png"):
                if (run / nm).exists():
                    q = sig(run / nm); used = nm
                    if q is not None:
                        break
            if q is None:
                continue
            sc = {u: float((q * s).mean()) for u, s in lib.items()}
            best = max(sc, key=sc.get)
            others = sorted((v for u, v in sc.items() if u != best), reverse=True)
            rows.append(dict(dataset=ds, run=run.name, claimed=claimed, best=best,
                             best_score=round(sc[best], 3),
                             claimed_score=round(sc.get(claimed, float("nan")), 3),
                             runner_up=round(others[0], 3) if others else np.nan,
                             margin=round(sc[best] - (others[0] if others else 0), 3),
                             reference=used, agrees=best == claimed))
            flag = "OK " if best == claimed else "!! "
            print(f"  {flag}{ds[-8:]} {run.name:26s} 라벨 {claimed:16s} "
                  f"최적 {best:16s} {sc[best]:.3f} (라벨 {sc.get(claimed, float('nan')):.3f}, "
                  f"2위 {others[0]:.3f})", flush=True)
    df = pd.DataFrame(rows)
    out = ROOT / "data" / "analysis" / "gel_identity.csv"
    df.to_csv(out, index=False)
    if len(df):
        print(f"\n  일치 {df.agrees.sum()}/{len(df)}  ->", out)
