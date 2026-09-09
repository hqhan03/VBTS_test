#!/usr/bin/env python3
"""Did BOTH posts of a paired-cylinder probe touch, and are they resolved?

A tilted pair mount loads one post: normal depth, normal force, an imprint that
looks fine in the log, and half the experiment silently gone (that is what
happened with pair100 on 2026-09-08). The log cannot see it because it records
one blob's area and centroid. This looks at the picture.

For each ladder image it differences against the run's reference, takes the
imprint region, and measures:

  aspect        major/minor second-moment axis of the imprint. Two 1 mm posts
                at 1.25-2.00 mm centres make an elongated patch (expect >= 1.6);
                one post alone is round (~1.0) -> TILT
  dip           relative depth of the valley between the two lobes along the
                major axis, 0 = merged, 1 = fully separated. This is the
                resolution measurement, not the seating check
  sep_px/mm     distance between the two lobe peaks when a valley exists

Usage: pair_check.py <run dir> [more run dirs]
"""
import sys, re, json
import numpy as np, pandas as pd, cv2
from pathlib import Path
from scipy import ndimage


def imprint(img, ref):
    d = img.astype(np.float32) - ref.astype(np.float32)
    d -= d.mean()
    a = cv2.GaussianBlur(np.abs(d), (0, 0), 5)
    thr = max(3.0, 0.35 * a.max())
    m = a > thr
    lab, n = ndimage.label(m)
    if n == 0:
        return None, None, None
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    k = int(np.argmax(sizes)) + 1
    return a, (lab == k), float(sizes[k - 1])


def measure(img_path, ref, ppm):
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    a, m, area = imprint(img, ref)
    if m is None or area < 50:
        return dict(file=img_path.name, area_px=0.0, aspect=np.nan, dip=np.nan)
    ys, xs = np.nonzero(m)
    y0, x0 = ys.mean(), xs.mean()
    cov = np.cov(np.vstack([xs - x0, ys - y0]))
    w, v = np.linalg.eigh(cov)
    major = v[:, int(np.argmax(w))]
    aspect = float(np.sqrt(max(w) / max(min(w), 1e-9)))
    # profile of the imprint's strength along the major axis
    t = (xs - x0) * major[0] + (ys - y0) * major[1]
    vals = a[ys, xs]
    lo, hi = t.min(), t.max()
    bins = np.linspace(lo, hi, 41)
    idx = np.clip(np.digitize(t, bins) - 1, 0, len(bins) - 2)
    prof = np.array([vals[idx == k].mean() if (idx == k).any() else 0.0
                     for k in range(len(bins) - 1)])
    prof = np.convolve(prof, np.ones(3) / 3, mode="same")
    # two peaks with a valley between them?
    mid = len(prof) // 2
    pk_l = prof[:mid].max() if mid else 0.0
    pk_r = prof[mid:].max() if mid else 0.0
    i_l = int(np.argmax(prof[:mid])); i_r = mid + int(np.argmax(prof[mid:]))
    valley = prof[i_l:i_r + 1].min() if i_r > i_l else min(pk_l, pk_r)
    peak = min(pk_l, pk_r)
    dip = float((peak - valley) / peak) if peak > 0 else np.nan
    sep = float(abs(bins[i_r] - bins[i_l]))
    return dict(file=img_path.name, area_px=area, aspect=aspect, dip=dip,
                sep_px=sep, sep_mm=sep / ppm if ppm else np.nan,
                major_px=float(hi - lo), minor_px=float(4 * np.sqrt(min(w))))


def check_run(run: Path, ppm=None):
    ref = None
    for nm in ("reference_working.png", "touchcheck.png", "reference.png"):
        if (run / nm).exists():
            ref = cv2.imread(str(run / nm), cv2.IMREAD_GRAYSCALE); break
    if ref is None:
        print(f"  {run.name}: no reference"); return None
    sh = sorted(run.glob("shape_pair*/*.png"))
    if not sh:
        print(f"  {run.name}: no pair ladder images"); return None
    rows = [measure(p, ref, ppm) for p in sh]
    df = pd.DataFrame(rows)
    print(f"\n  {run.name}  ({len(df)} rungs, reference {nm})")
    print(f"    {'image':28s} {'area px':>9} {'aspect':>7} {'dip':>6} {'sep mm':>7}")
    for _, r in df.iterrows():
        print(f"    {r.file:28s} {r.area_px:9.0f} {r.aspect:7.2f} {r.dip:6.2f} "
              f"{r.get('sep_mm', float('nan')):7.2f}")
    deep = df[df.area_px > 200]
    verdict = "no contact"
    if len(deep):
        asp = deep.aspect.max()
        verdict = ("TILT? one post only (aspect %.2f < 1.5)" % asp if asp < 1.5
                   else "both posts loaded (aspect %.2f)" % asp)
    print(f"    -> {verdict}")
    return df


if __name__ == "__main__":
    for d in sys.argv[1:]:
        check_run(Path(d))
