#!/usr/bin/env python3
"""Spatial bandwidth of what the camera has to resolve, per unit.

Two quantities, both as the spatial frequency below which 90 % of the
(noise-subtracted) image energy lies, in cycles/mm, from Pass B ball8 frames:

  normal   the imprint itself: (frame - reference) at 1.6-2.1 N
  shear    what SHEAR adds: (sheared frame) - (least-sheared frame of the same
           cycle), DC removed -- the dipole, with the normal-load monopole gone

The noise spectrum is measured from two normal-block frames at the same Fz and
subtracted, and the spectrum is restricted to 0-3 cycles/mm where the signal
lives (white sensor noise dominates the total energy otherwise). Nyquist then
puts the pixel requirement across the 19 mm field at 2 x f90 x 19.

Why this exists: the force-vs-resolution sweep found Fz flat down to 16x9 and
shear breaking earlier, and the question was whether that is the model or the
pictures. It is the pictures. force_estimation.md 2.3b quotes these numbers.
"""
import argparse
import glob
import os
import re
import yaml
import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RUNS = os.path.join(ROOT, "data", "20260911_VBTSresolution_dataset", "9DTact", "20260907_passB_ball8")
# px/mm at full resolution. 9DTact ran with a fixed 100 (scale.yaml gives
# 96-104); DIGIT and DIGIT_Marker differ enough per unit (83-117) that the
# per-unit value from derived_variables.csv is used when it is there, since
# cycles/mm is only comparable if the scale is right.
PPM = 100.0
HARD = {"soft": 0, "medium": 1, "hard": 2}
FMAX, DF = 3.0, 0.1


def set_ppm(v):
    global PPM
    PPM = float(v)


def radial(P):
    H, W = P.shape
    y, x = np.mgrid[0:H, 0:W]
    f = np.hypot((x - W / 2) / W, (y - H / 2) / H) * (PPM / 2)   # half-res
    bins = np.arange(0, FMAX + DF / 2, DF)
    idx = np.digitize(f.ravel(), bins)
    return bins[1:], np.array([P.ravel()[idx == k].sum() for k in range(1, len(bins))])


def spec(a, b):
    d = (a.astype(np.float32) - b.astype(np.float32))[::2, ::2]
    d -= d.mean()
    return np.abs(np.fft.fftshift(np.fft.fft2(d))) ** 2


def f90(fb, S, N):
    sig = np.clip(S - N, 0, None)
    cs = np.cumsum(sig) / max(sig.sum(), 1e-9)
    return float(fb[np.searchsorted(cs, 0.90)])


def unit(D, nsamp=10):
    fr = pd.read_csv(os.path.join(D, "stream", "frames.csv"))
    fz = fr.Fz_s_corr if "Fz_s_corr" in fr else fr.Fz_s
    fx = fr.Fx_s_corr if "Fx_s_corr" in fr else fr.Fx_s
    fy = fr.Fy_s_corr if "Fy_s_corr" in fr else fr.Fy_s
    fr["fz"] = fz.abs()
    fr["lat"] = np.hypot(fx, fy)
    nrm = fr[fr.segment.astype(str).str.startswith("normal")]
    shr = fr[fr.segment.astype(str).str.startswith("shear")]
    rd = lambda f: cv2.imread(os.path.join(D, "stream", f), cv2.IMREAD_GRAYSCALE)
    # reference_collect.png first: on every DIGIT run reference.png is 8-14 %
    # brighter than the frames (campaign_protocol.md 4.7 (10)), which would put
    # a field-wide pedestal into the "imprint" spectrum.
    ref = None
    for nm in ("reference_collect.png", "reference_working.png", "reference.png"):
        if os.path.exists(os.path.join(D, nm)):
            ref = cv2.imread(os.path.join(D, nm), cv2.IMREAD_GRAYSCALE); break
    out = {}
    # normal imprint at ~2 N, noise from two normal frames at the same Fz
    Sn = Nn = None
    for _, r in nrm[(nrm.fz > 1.6) & (nrm.fz < 2.1)].sample(nsamp, random_state=0).iterrows():
        cand = nrm[(nrm.fz - r.fz).abs() < 0.12]
        if len(cand) < 2:
            continue
        c = cand.sample(2, random_state=1)
        a, b, b2 = rd(r["file"]), rd(c.iloc[0]["file"]), rd(c.iloc[1]["file"])
        fb, s = radial(spec(a, ref)); _, n = radial(spec(b, b2))
        Sn = s if Sn is None else Sn + s; Nn = n if Nn is None else Nn + n
    out["normal_f90"] = f90(fb, Sn, Nn)
    # shear dipole: sheared frame minus the least-sheared frame of its own cycle
    Ss = Ns = None
    for _, r in shr[shr.lat > 0.35].sample(nsamp, random_state=0).iterrows():
        same = shr[(shr.cycle == r.cycle) & (shr.index != r.name)]
        if same.empty:
            continue
        j = same.lat.idxmin()
        cand = nrm[(nrm.fz - r.fz).abs() < 0.12]
        if len(cand) < 2:
            continue
        c = cand.sample(2, random_state=2)
        fb, s = radial(spec(rd(r["file"]), rd(shr.loc[j, "file"])))
        _, n = radial(spec(rd(c.iloc[0]["file"]), rd(c.iloc[1]["file"])))
        Ss = s if Ss is None else Ss + s; Ns = n if Ns is None else Ns + n
    out["shear_f90"] = f90(fb, Ss, Ns)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", default=DEFAULT_RUNS, help="Pass B dataset folder")
    ap.add_argument("--principle", default=None, help="default: from the folder path")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    principle = a.principle or os.path.basename(os.path.dirname(a.runs))
    out = a.out or os.path.join(a.runs, "..", "imprint_bandwidth.csv")

    # one run per unit, and the per-unit scale
    can = os.path.join(a.runs, "CANONICAL.yaml")
    if os.path.exists(can):
        with open(can) as fh:
            c = yaml.safe_load(fh)["canonical"]
        runs = [(u.replace(principle + "_", ""), os.path.join(a.runs, v["run"]))
                for u, v in c.items() if v.get("run")]
    else:
        runs = [(os.path.basename(D).replace(principle + "_", ""), D)
                for D in sorted(glob.glob(os.path.join(a.runs, principle + "_*")))
                if not re.search(r"__\d+$", D)]
    scale = {}
    dv = os.path.join(ROOT, "data", "analysis", "derived_variables.csv")
    if os.path.exists(dv):
        d = pd.read_csv(dv)
        d = d[d.principle == principle]
        scale = dict(zip(d.unit, d.px_per_mm))

    rows = []
    for u, D in runs:
        ppm = scale.get(u)
        set_ppm(ppm if ppm and np.isfinite(ppm) else 100.0)
        o = unit(D)
        rows.append(dict(unit=u, principle=principle, hard=HARD[u.split("_")[0]],
                         th=int(u.split("_")[1][0]), px_per_mm=PPM, **o))
        print(f"  {u:16s} ppm {PPM:6.1f}  normal f90 {o['normal_f90']:.2f}   "
              f"shear f90 {o['shear_f90']:.2f}  cyc/mm", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    for col in ("normal_f90", "shear_f90"):
        v = df[col]
        h = spearmanr(df.hard, v); t = spearmanr(df.th, v)
        print(f"\n  {col}: {v.min():.2f}-{v.max():.2f} cyc/mm ({v.max()/v.min():.2f}x)  "
              f"-> Nyquist {2*v.min()*19:.0f}-{2*v.max()*19:.0f} px across 19 mm")
        print(f"    hardness rho {h.statistic:+.3f} p {h.pvalue:.3f}   "
              f"thickness rho {t.statistic:+.3f} p {t.pvalue:.3f}")
    print("  ->", os.path.normpath(out))
