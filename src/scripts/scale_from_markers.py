#!/usr/bin/env python3
"""Image scale from a DIGIT_Marker gel's own dot grid.

The marker units carry a printed grid: black dots 1.0 mm across on a 2.5 mm
square pitch, set 0.5 mm below the gel's top surface. That is a ruler lying in
every frame, and it makes the scale free -- no robot, no pressing, no tracking.
It is read straight off `reference.png`, which every run already captures.

Two lengths come out of one picture and they are made by different parts of the
process, so their agreement is a check that costs nothing: the dot PITCH (a
property of the artwork) and the dot DIAMETER (a property of the printing).
Measured 2026-09-08 on DIGIT_Marker_hard_3mm_r1 they give 97.57 and 98.66
px/mm, 1.1 % apart.

DO NOT USE THIS AS THE SCALE YET
--------------------------------
It disagrees with everything else by 15 %, and the everything else is on firmer
ground. Across the 18 non-marker DIGIT units the image scale is a very tight
function of the gel's surface height -- kx = -12.44 x surface + 403.1, r =
-0.994, residual 1.01 px/mm -- because a higher surface is further from the
camera. `DIGIT_Marker_hard_3mm_r1`'s surface of 25.584 mm predicts 84.96 px/mm.
The cross-correlation measured 82.83 (2.1 sigma low); this grid says 97.57
(12.4 sigma high).

Being 0.5 mm nearer the camera than the contact surface explains +6.2 px/mm of
that on the same slope, which leaves 6 % unaccounted. The pitch and the dot
diameter agree with each other to 1.1 %, so if the artwork is not at its
nominal 2.5 mm and 1.0 mm -- print scaling, or the gel shrinking as it cures --
both are wrong by the same factor and this measurement inherits it. A 7 %
shrink would put the real pitch at 2.33 mm.

Settling it needs a scale that does not come from the artwork, which is what
the pair100 caliper is: press it on a marker unit and the grid's true pitch
falls out. Until then this reports a number and does not claim it.

WHAT THIS SCALE BELONGS TO
--------------------------
The marker plane, not the contact surface. The dots sit 0.5 mm below the top of
the gel, so they are 0.5 mm further from the camera than the place the probe
touches, and on a 25 mm working distance that is about 2 % of magnification.
Whether to correct for it is a decision for the analysis that uses the number;
this reports the marker-plane scale and says so.

    scale_from_markers.py <reference.png> [more.png ...]
"""
import sys
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np

PITCH_MM = 2.5
DOT_MM = 1.0


def grid_scale(bgr, illum_sigma=80.0, thresh=0.45, open_px=15,
               area_lo=2000, area_hi=40000):
    """px/mm from the dot pitch and from the dot diameter, plus the grid's axes.

    The illumination across a DIGIT frame varies more than the dots do -- three
    coloured LEDs from three sides -- so the dots are found against a heavily
    blurred copy of the frame rather than against a fixed level. What survives
    is local darkness, which is what a dot is.
    """
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    d = cv2.GaussianBlur(g, (0, 0), illum_sigma) - g      # dots are dark
    rng = d.max() - d.min()
    if rng <= 0:
        return None
    d = (d - d.min()) / rng
    m = cv2.morphologyEx((d > thresh).astype(np.uint8), cv2.MORPH_OPEN,
                         np.ones((open_px, open_px), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m, 8)
    keep = [i for i in range(1, n) if area_lo < st[i, cv2.CC_STAT_AREA] < area_hi]
    if len(keep) < 6:
        return None
    C = np.array([cen[i] for i in keep])
    A = np.array([st[i, cv2.CC_STAT_AREA] for i in keep], dtype=float)
    # nearest-neighbour distances: on a square grid the two nearest are one
    # pitch away along the two axes, and the diagonal is 1.41 pitch, so taking
    # the two nearest of each dot samples the pitch and nothing else.
    nn, vecs = [], []
    for c in C:
        dv = C - c
        r = np.hypot(dv[:, 0], dv[:, 1])
        o = np.argsort(r)[1:3]
        nn += list(r[o])
        vecs += list(dv[o])
    nn = np.array(nn)
    V = np.array(vecs)
    pitch_px = float(np.median(nn))
    dot_px = float(2 * np.sqrt(np.median(A) / np.pi))
    ang = np.degrees(np.arctan2(V[:, 1], V[:, 0])) % 90.0   # square grid: mod 90
    return dict(n_dots=len(keep), pitch_px=pitch_px, dot_px=dot_px,
                px_per_mm_pitch=pitch_px / PITCH_MM,
                px_per_mm_dot=dot_px / DOT_MM,
                pitch_iqr_px=float(np.percentile(nn, 75) - np.percentile(nn, 25)),
                grid_angle_deg=float(np.median(ang)))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[-1])
        return 2
    print(f"{'file':44}{'dots':>6}{'pitch px':>10}{'dot px':>8}"
          f"{'px/mm pitch':>13}{'px/mm dot':>11}{'diff':>7}{'grid deg':>10}")
    for p in sys.argv[1:]:
        im = cv2.imread(p)
        if im is None:
            print(f"{Path(p).name:44}  unreadable")
            continue
        r = grid_scale(im)
        if r is None:
            print(f"{Path(p).name:44}  no grid found")
            continue
        diff = 100 * abs(r["px_per_mm_pitch"] - r["px_per_mm_dot"]) / r["px_per_mm_pitch"]
        print(f"{Path(p).parent.parent.name[:44]:44}{r['n_dots']:6d}"
              f"{r['pitch_px']:10.1f}{r['dot_px']:8.1f}"
              f"{r['px_per_mm_pitch']:13.2f}{r['px_per_mm_dot']:11.2f}"
              f"{diff:6.1f}%{r['grid_angle_deg']:10.1f}")
    print("\n  This is the MARKER-PLANE scale: the dots sit 0.5 mm below the "
          "contact surface,\n  which is about 2 % of magnification at this "
          "working distance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
