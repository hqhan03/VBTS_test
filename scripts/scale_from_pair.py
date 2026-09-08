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


def two_posts(d, sigma=None, excl=110, border_frac=0.06, ratio=15.0):
    """The two posts, as the two strongest maxima of the smoothed difference.

    NOT connected components, and the difference matters. Each post leaves a
    bright halo with a strong core, so a threshold low enough to hold a whole
    post joins the two halos into one region, and one high enough to separate
    them breaks each core into pieces. Sweeping the threshold from 8 to 24 on a
    single DIGIT_hard_3mm_r1 picture gave separations of 220, 0, 121, 194, 97,
    96, 0, 0 px (2026-09-08), and on that evidence this file previously
    concluded that a soft gel fills in between posts 2 mm apart and that
    pair100 could not serve as a caliper. That conclusion was wrong, and the
    operator caught it by looking at the picture: the two posts are plainly
    there and plainly separate. The fault was reducing a two-peak scene by
    connectivity instead of by its peaks.

    Smoothing hard (sigma 20 px, well under the ~185 px separation and well
    over the core texture) and taking the two strongest maxima, with the second
    sought outside `excl` of the first, gives 0.7 % agreement between two
    frames of the same press and a direction that tracks the commanded tool
    roll. `border_frac` keeps the frame edge out of it -- there is a vignetting
    blob in the top-right corner of every DIGIT frame that is larger than a
    post and was being picked as one.
    """
    # SIGMA IS NOT FREE. Smoothing pulls the two peaks together, and by enough
    # to matter: on the 9DTact pair presses, where the trusted scale says the
    # answer should be 1.000, this returns 1.021 at sigma 8 and 0.906 at sigma
    # 26 -- monotone, 12 % across the range. A fixed sigma 20 is what made this
    # file report the 9DTact scale 6 % short and call it a systematic offset.
    # So measure once at sigma 10, then set sigma to separation/15 and measure
    # again: the smoothing stays a fixed fraction of the thing being measured
    # whatever its size. DIGIT_hard_3mm_r1 is insensitive to the choice
    # (93.9-94.7 px/mm over sigma 8 to 26) because its posts separate cleanly;
    # the 9DTact imprints are the ones that need it.
    if sigma is None:
        first = two_posts(d, sigma=10.0, excl=excl, border_frac=border_frac)
        if first is None:
            return None
        sigma = float(np.clip(first["sep_px"] / ratio, 6.0, 25.0))
    g = cv2.GaussianBlur(d, (0, 0), sigma).copy()
    h, w = g.shape
    mx, my = int(w * border_frac), int(h * border_frac)
    g[:my] = 0
    g[-my:] = 0
    g[:, :mx] = 0
    g[:, -mx:] = 0
    out = []
    for _ in range(2):
        y, x = np.unravel_index(int(np.argmax(g)), g.shape)
        pk = float(g[y, x])
        if pk <= 0:
            return None
        sx = sy = 0.0
        if 0 < x < w - 1:
            den = g[y, x - 1] - 2 * g[y, x] + g[y, x + 1]
            sx = 0.0 if abs(den) < 1e-9 else 0.5 * (g[y, x - 1] - g[y, x + 1]) / den
        if 0 < y < h - 1:
            den = g[y - 1, x] - 2 * g[y, x] + g[y + 1, x]
            sy = 0.0 if abs(den) < 1e-9 else 0.5 * (g[y - 1, x] - g[y + 1, x]) / den
        out.append((x + float(np.clip(sx, -1, 1)), y + float(np.clip(sy, -1, 1)), pk))
        cv2.circle(g, (int(x), int(y)), excl, 0, -1)
    (x1, y1, p1), (x2, y2, p2) = out
    v = np.array([x2 - x1, y2 - y1])
    if not (-90 < np.degrees(np.arctan2(v[1], v[0])) <= 90):
        v = -v
    return dict(vec=v, sep_px=float(np.hypot(*v)),
                axis_deg=float(np.degrees(np.arctan2(v[1], v[0]))),
                sym=float(min(p1, p2) / max(p1, p2)), peak=float(min(p1, p2)))


def fit_ellipse(vecs, S, max_reject=3, tol=0.05):
    """J's shape from a set of caliper vectors, up to a rotation.

    Every press satisfies |J^-1 v| = S, so the v's lie on an ellipse and its
    axes are J's singular values. Nothing here needs the commanded angle, or
    the posts' direction in the sensor frame -- only that the directions are
    spread. What the ellipse cannot give is the rotation between sensor and
    image, which the scale phase measures well even when its magnitudes wander.
    """
    V = np.asarray(vecs, dtype=float)
    keep = np.ones(len(V), bool)
    for _ in range(max_reject + 1):
        M = np.stack([V[:, 0] ** 2, 2 * V[:, 0] * V[:, 1], V[:, 1] ** 2], 1)
        c, *_ = np.linalg.lstsq(M[keep], np.ones(int(keep.sum())), rcond=None)
        r = np.abs(M @ c - 1.0)
        rms = float(np.sqrt((r[keep] ** 2).mean()))
        if rms <= tol or keep.sum() <= 5:
            break
        r2 = r.copy()
        r2[~keep] = -1
        keep[int(np.argmax(r2))] = False
    A = np.array([[c[0], c[1]], [c[1], c[2]]])
    w, U = np.linalg.eigh(np.linalg.inv(A) / S ** 2)
    i = np.argsort(w)[::-1]
    sv = np.sqrt(np.clip(w[i], 1e-12, None))
    return dict(sv=sv, anisotropy=float(sv[0] / sv[1]),
                isotropic_px_per_mm=float(np.sqrt(sv[0] * sv[1])),
                major_deg=float(np.degrees(np.arctan2(U[1, i[0]], U[0, i[0]]))),
                rms=rms, n_used=int(keep.sum()), n=len(V), keep=keep)


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
                d = difference(img, ref, shadows_the_gel(sensor), blur=0)
                got = two_posts(d)
                if got is None:
                    continue
                sym, amin, v = got["sym"], 0, got["vec"]
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


def solve(run_dir: Path, probe: str, S: float, sym_min=0.6) -> int:
    """Fit the ellipse from every caliper press under `run_dir`.

    Each `scale_<probe>*` directory is one tool orientation; the frames inside
    it are repeats. The ellipse needs the DIRECTIONS spread, not known, so any
    set of reachable rolls will do -- which matters, because the wrist can only
    unwind one way from some poses and the commanded angle is relative to
    wherever the tool was left.
    """
    run = Path(run_dir)
    ref = cv2.imread(str(run / "reference.png"))
    if ref is None:
        print(f"no reference.png in {run}")
        return 1
    sid = None
    if (run / "meta.yaml").exists():
        import yaml
        sid = (yaml.safe_load((run / "meta.yaml").read_text()) or {}).get("sensor_id")
    colour = shadows_the_gel(sid)
    rows, vecs = [], []
    for d in sorted(run.glob(f"scale_{probe}*")):
        for f in sorted(d.glob("*.png")):
            g = two_posts(difference(cv2.imread(str(f)), ref, colour, blur=0))
            if g is None or g["sym"] < sym_min:
                rows.append((d.name, f.name, None, None, None))
                continue
            rows.append((d.name, f.name, g["sep_px"], g["axis_deg"], g["sym"]))
            vecs.append(g["vec"])
    print(f"  {sid or run.name}, probe {probe}, S = {S:.2f} mm")
    print(f"    {'orientation':26} {'sep px':>8} {'axis':>8} {'sym':>6}")
    for dn, fn, sep, ax, sym in rows:
        if sep is None:
            print(f"    {dn:26} {'--':>8}")
        else:
            print(f"    {dn:26} {sep:8.1f} {ax:+8.1f} {sym:6.2f}")
    if len(vecs) < 4:
        print(f"\n  only {len(vecs)} usable presses; the ellipse needs at least four "
              "spread directions")
        return 1
    e = fit_ellipse(vecs, S)
    ang = np.degrees(np.arctan2([v[1] for v in vecs], [v[0] for v in vecs]))
    print(f"\n  directions span {ang.ptp():.0f} deg over {len(vecs)} presses")
    print(f"  ellipse residual {e['rms']:.4f} on {e['n_used']}/{e['n']}")
    print(f"  px/mm along the principal axes   {e['sv'][0]:.2f} / {e['sv'][1]:.2f}")
    print(f"  anisotropy                       {e['anisotropy']:.3f}")
    print(f"  isotropic-equivalent scale       {e['isotropic_px_per_mm']:.2f} px/mm"
          f"  ({1000 / e['isotropic_px_per_mm']:.3f} um/px)")
    print(f"  major axis in the image          {e['major_deg']:+.1f} deg")
    print("\n  This fixes J's SHAPE, not its rotation: a caliper cannot tell which "
          "sensor\n  direction the posts lay along. Take the rotation from the "
          "scale phase, which\n  determines it well even where its magnitudes wander.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true",
                    help="check the method against the 9DTact trusted scales")
    ap.add_argument("--run", default=None, help="run directory to solve")
    ap.add_argument("--probe", default="pair100")
    ap.add_argument("--gap", type=float, default=None,
                    help="post centre spacing in mm; defaults to the probe's")
    a = ap.parse_args()
    if a.validate:
        return validate()
    if a.run:
        return solve(Path(a.run), a.probe, a.gap or GAPS.get(a.probe, 2.0))
    ap.error("give --validate or --run")


if __name__ == "__main__":
    raise SystemExit(main())
