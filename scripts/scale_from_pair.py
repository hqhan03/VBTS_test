#!/usr/bin/env python3
"""Image scale from a paired-cylinder probe, the way DIGIT's own tooling does it.

WHY NOT THE ROBOT-AS-RULER METHOD
---------------------------------
`run_indentation.py --phase scale` moves the arm a known distance and tracks
the imprint by cross-correlation. That needs an imprint with texture to hold
on to. A 9DTact has one; a DIGIT does not -- its imprint is a smooth colour
blob, and three repeats of the scale phase on DIGIT_hard_3mm_r1 gave
87.4 / 91.7 / 95.6 px/mm, an 8.6 % spread against the 9DTact's 5 %, with one
run losing a correlation outright.

The reference DIGIT pipeline (vocdex/digit-depth) does not infer length from
motion at all: it presses a CALIPER into the gel and reads the known gap off
the picture. This is that idea with the caliper we already own.

THE MEASUREMENT
---------------
A pair probe is two 1 mm posts whose centre-to-centre spacing S is a design
number (2.00, 1.75, 1.50, 1.25 mm). Press it and the image shows two blobs.
With `v` the pixel vector between their centres and `u` the unit vector along
the posts in the sensor frame,

    v = J @ (S * u)

so each press gives two equations in the four unknowns of J. Press at three or
more tool rotations and J falls out of a least-squares fit, with the residual
as a self-check that costs nothing.

Two properties make the centres the right feature. They do not move when the
blobs dilate -- and the detected contact region on this rig is systematically
about 1.25x larger than the true one (`shape_reconstruction.md`), which is why
diameters cannot be used. And every press is independent, so nothing
accumulates: the F/T drift that fooled the search, and the frame-to-frame
correlation that fooled the scale, have no analogue here.

    scale_from_pair.py --validate     # check the method against trusted scales
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import analyse_resolution as A          # noqa: E402
from run_indentation import shadows_the_gel  # noqa: E402

GAPS = {"pair100": 2.00, "pair075": 1.75, "pair050": 1.50, "pair025": 1.25}
ELEMENT_MM = 1.0                        # post diameter; S = gap + element


def difference(frame_bgr, ref_bgr, colour: bool, blur: int = 5):
    """The picture the blobs are found in, reduced the way this principle needs.

    Blurred first, as `contact_region` does. Skipping it costs almost
    everything: without the blur, single-pixel noise survives the threshold as
    speckle, the 9x9 opening then removes the speckle AND the signal with it,
    and 155 of 204 pair presses came back with no blobs at all -- on frames
    whose own ladder row recorded thousands of pixels of contact.
    """
    if colour:
        f = frame_bgr.astype(np.float32) - ref_bgr.astype(np.float32)
        f -= f.mean(axis=(0, 1), keepdims=True)
        d = np.abs(f).max(axis=2)
    else:
        g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        r = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        d = np.clip(r - g, 0, None)      # 9DTact contact darkens
    return cv2.GaussianBlur(d, (blur | 1, blur | 1), 0) if blur > 1 else d


def two_blobs(d, level, min_area=300, sym_min=0.35):
    """Centres of the two posts, or None if they are not two separate things.

    Intensity-weighted centroids, not the connected-component centroid: the
    posts press unequally (weak/strong 0.45-0.96 across this campaign) and a
    binary centroid throws away the shape that says where the middle of the
    weaker one is.
    """
    m = cv2.morphologyEx((d >= level).astype(np.uint8), cv2.MORPH_OPEN,
                         np.ones((9, 9), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    blobs = sorted([i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= min_area],
                   key=lambda i: -st[i, cv2.CC_STAT_AREA])[:2]
    if len(blobs) < 2:
        return None
    a1, a2 = (st[b, cv2.CC_STAT_AREA] for b in blobs)
    if min(a1, a2) / max(a1, a2) < sym_min:
        return None                     # one post barely touched; its centre is noise
    cs = []
    for b in blobs:
        w = np.where(lab == b, d, 0.0)
        tot = w.sum()
        ys, xs = np.mgrid[0:d.shape[0], 0:d.shape[1]]
        cs.append((float((w * xs).sum() / tot), float((w * ys).sum() / tot)))
    return np.array(cs), (float(min(a1, a2) / max(a1, a2)), int(min(a1, a2)))


def peak_pair(d, level=10, border_frac=0.06, blur=21, half_win=25):
    """Separation and direction of the two posts, from the PROFILE not the blobs.

    Thresholding into two connected components cannot work here. Measured
    2026-09-08 on DIGIT_hard_3mm_r1 with pair100 properly aligned: the trough
    between the posts sits at 8-11 grey levels and the peaks at 14-26, so a
    threshold below the trough merges them into one region and a threshold
    above it fragments each post into pieces. Sweeping the threshold gave 220,
    0, 121, 194, 97, 96, 0, 0 px for the same picture. There is no value that
    works, and that is not a tuning problem -- a soft gel fills in between two
    posts 2 mm apart, which is the same reason only 11 of 17 9DTact units
    resolve this gap at all.

    The two posts ARE there: the profile across them has a dip of 0.40-0.48,
    well over the 0.265 the resolution test asks for. So take the profile and
    find its two maxima, which is what the resolution analysis already does --
    with the difference that here their POSITIONS are the measurement, and are
    left free rather than sought at the known separation.
    """
    h, w = d.shape
    g = cv2.GaussianBlur(d, (blur | 1, blur | 1), 0)
    mx, my = int(w * border_frac), int(h * border_frac)
    m = cv2.morphologyEx((g >= level).astype(np.uint8), cv2.MORPH_OPEN,
                         np.ones((9, 9), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m, 8)
    ok = [i for i in range(1, n)
          if st[i, cv2.CC_STAT_LEFT] >= mx and st[i, cv2.CC_STAT_TOP] >= my
          and st[i, cv2.CC_STAT_LEFT] + st[i, cv2.CC_STAT_WIDTH] <= w - mx
          and st[i, cv2.CC_STAT_TOP] + st[i, cv2.CC_STAT_HEIGHT] <= h - my]
    if not ok:
        return None
    k = max(ok, key=lambda i: st[i, cv2.CC_STAT_AREA])
    cx, cy = cen[k]
    ys, xs = np.nonzero(lab == k)
    pts = np.stack([xs - cx, ys - cy]).astype(np.float64)
    ax = np.linalg.svd(pts @ pts.T / len(xs))[0][:, 0]     # long axis of the pair
    reach = int(0.75 * max(st[k, cv2.CC_STAT_WIDTH], st[k, cv2.CC_STAT_HEIGHT]))
    z = np.arange(-reach, reach + 1, dtype=float)
    px = np.clip(np.round(cx + ax[0] * z).astype(int), 0, w - 1)
    py = np.clip(np.round(cy + ax[1] * z).astype(int), 0, h - 1)
    prof = g[py, px]
    mid = np.abs(z) <= half_win
    if not mid.any():
        return None
    trough = float(prof[mid].min())
    out = []
    for sel in (z > half_win, z < -half_win):
        if not sel.any():
            return None
        i = int(np.argmax(prof[sel]))
        zz, pp = z[sel], prof[sel]
        # parabolic vertex on the three samples around the maximum
        if 0 < i < len(pp) - 1:
            den = pp[i - 1] - 2 * pp[i] + pp[i + 1]
            sub = 0.0 if abs(den) < 1e-9 else 0.5 * (pp[i - 1] - pp[i + 1]) / den
        else:
            sub = 0.0
        out.append((float(zz[i] + sub), float(pp[i])))
    (z1, p1), (z2, p2) = out
    peak = min(p1, p2)
    if peak <= 0:
        return None
    sep = abs(z1 - z2)
    return dict(sep_px=sep, axis_deg=float(np.degrees(np.arctan2(ax[1], ax[0]))),
                vec=np.array([ax[0] * (z1 - z2), ax[1] * (z1 - z2)]),
                dip=float(1.0 - trough / peak), sym=float(min(p1, p2) / max(p1, p2)),
                peak=peak, centre=(float(cx), float(cy)))


def validate() -> int:
    """|J^-1 v| / S must be 1 if the method and the trusted scale agree.

    The tool orientation was never varied in Pass A, so J cannot be SOLVED from
    those runs -- but it can be TESTED against them, and this test needs no
    knowledge of the angle at all.
    """
    rows = []
    for probe, gap in GAPS.items():
        S = gap
        ds = ROOT / "data" / "9DTact" / f"20260905_passA_{probe}"
        if not ds.exists():
            continue
        for run in sorted(ds.iterdir()):
            lad = run / f"shape_{probe}" / "ladder.csv"
            if not lad.exists() or "__" in run.name:
                continue
            sensor = run.name
            try:
                J = A.jacobian(json.loads((run / "state.json").read_text()), sensor)
            except Exception:
                J = None
            if J is None:
                continue
            ref = cv2.imread(str(run / "reference.png"))
            L = pd.read_csv(lad)
            lvl = int(L.diff_level.iloc[0])
            for _, r in L.iterrows():
                img = cv2.imread(str(run / f"shape_{probe}" / r.file))
                if img is None:
                    continue
                d = difference(img, ref, shadows_the_gel(sensor))
                got = two_blobs(d, lvl)
                if got is None:
                    continue
                (c, (sym, amin)) = got
                v = c[1] - c[0]
                u = np.linalg.solve(J, v) / S
                rows.append(dict(sensor=sensor.replace("9DTact_", ""), probe=probe,
                                 S=S, depth=float(r.target_depth_mm),
                                 sep_px=float(np.hypot(*v)), ratio=float(np.hypot(*u)),
                                 sym=sym, min_area=amin))
    df = pd.DataFrame(rows)
    if df.empty:
        print("no pair presses with a trusted scale")
        return 1
    out = ROOT / "data" / "9DTact" / "scale_from_pair_validation.csv"
    df.to_csv(out, index=False)
    print(f"{len(df)} presses over {df.sensor.nunique()} units and "
          f"{df.probe.nunique()} probes -> {out.name}\n")
    print("  |J^-1 v| / S, which is 1.00 if the trusted scale and this method agree")
    g = df.groupby("probe").ratio.agg(["size", "median", "std",
                                       lambda s: s.quantile(.75) - s.quantile(.25)])
    g.columns = ["n", "median", "sd", "IQR"]
    print(g.round(3).to_string())
    print(f"\n  all: n={len(df)}  median {df.ratio.median():.3f}  "
          f"IQR {df.ratio.quantile(.75) - df.ratio.quantile(.25):.3f}  "
          f"sd {df.ratio.std():.3f}")
    good = df[df.sym >= 0.6]
    print(f"  posts within 40 % of each other (sym>=0.6): n={len(good)}  "
          f"median {good.ratio.median():.3f}  "
          f"IQR {good.ratio.quantile(.75) - good.ratio.quantile(.25):.3f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    if a.validate:
        return validate()
    ap.error("nothing to do yet: --validate is the only mode implemented")


if __name__ == "__main__":
    raise SystemExit(main())
