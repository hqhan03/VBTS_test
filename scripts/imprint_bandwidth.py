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
import glob
import os
import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "data", "9DTact", "20260907_passB_ball8")
PPM = 100.0          # px/mm at full resolution, 9DTact (scale.yaml ~ 96-104)
HARD = {"soft": 0, "medium": 1, "hard": 2}
FMAX, DF = 3.0, 0.1


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
    fr["fz"] = fr.Fz_s_corr.abs()
    fr["lat"] = np.hypot(fr.Fx_s_corr, fr.Fy_s_corr)
    nrm = fr[fr.segment.astype(str).str.startswith("normal")]
    shr = fr[fr.segment.astype(str).str.startswith("shear")]
    rd = lambda f: cv2.imread(os.path.join(D, "stream", f), cv2.IMREAD_GRAYSCALE)
    ref = cv2.imread(os.path.join(D, "reference.png"), cv2.IMREAD_GRAYSCALE)
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
    rows = []
    for D in sorted(glob.glob(os.path.join(RUNS, "9DTact_*"))):
        u = os.path.basename(D).replace("9DTact_", "")
        o = unit(D)
        rows.append(dict(unit=u, hard=HARD[u.split("_")[0]], th=int(u.split("_")[1][0]), **o))
        print(f"  {u:16s} normal f90 {o['normal_f90']:.2f}   shear f90 {o['shear_f90']:.2f}  cyc/mm")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(ROOT, "data", "9DTact", "imprint_bandwidth.csv"), index=False)
    for col in ("normal_f90", "shear_f90"):
        v = df[col]
        h = spearmanr(df.hard, v); t = spearmanr(df.th, v)
        print(f"\n  {col}: {v.min():.2f}-{v.max():.2f} cyc/mm ({v.max()/v.min():.2f}x)  "
              f"-> Nyquist {2*v.min()*19:.0f}-{2*v.max()*19:.0f} px across 19 mm")
        print(f"    hardness rho {h.statistic:+.3f} p {h.pvalue:.3f}   thickness rho {t.statistic:+.3f} p {t.pvalue:.3f}")
    print("  -> data/9DTact/imprint_bandwidth.csv")
