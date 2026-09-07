#!/usr/bin/env python3
"""Test 3: are the two cylinders resolved, and at what depth?

    analyse_resolution.py <dataset> <sensor_id> [pair_id ...]

THE CRITERION IS FIXED HERE, BEFORE ANY PAIR DATA EXISTS. That is the whole
point of writing this now: a threshold chosen after seeing the images is not a
measurement, it is a preference.

  observable   the darkening profile, ref - img, taken along the line joining
               the two elements and averaged over a band across it. The
               question asked was whether the two cylinders LOOK separated, so
               the image is the right thing to measure, not a reconstruction.
  criterion    Two are reported, and BOTH were fixed before any pair data
               existed.

               RAYLEIGH: resolved when the trough between the two peaks falls
               at least 26.5 % below their mean height. That number is not
               ours to choose -- it is the classical resolution limit, the dip
               two equal Airy patterns show when one's maximum sits on the
               other's first zero.

               MTF >= 0.5: the criterion Digit 360 used (arXiv:2411.02479),
               pressing a dual-pronged microindenter and inspecting the taxel
               intensity line profile -- the same experiment as this one. MTF
               here is Michelson contrast, (peak - trough) / (peak + trough).
               It is much the stricter of the two: with T = P(1 - D),
               M = D / (2 - D), so M >= 0.5 means D >= 0.667, two and a half
               times the Rayleigh dip. Reporting both is what makes our numbers
               comparable to theirs without abandoning the criterion this file
               fixed first.
  noise gate   a dip only counts if it exceeds three times its own
               uncertainty, so noise cannot manufacture a separation. That
               uncertainty comes from the profile itself -- the successive-
               difference estimate of its per-sample noise, propagated through
               1 - trough/peak -- because the ladder is walked ONCE now and
               there is no across-pass scatter to use. This matters more than
               it sounds: the dip is measured with max() in the peak windows
               and min() in the trough, and extrema are biased apart by noise,
               so noise does not merely blur the dip, it manufactures one.

Geometry: `gap_mm` in probes.yaml is EDGE to edge -- a 0.25 mm centre spacing
would have two 1 mm cylinders overlapping -- so the separation being tested is
1.0 + gap, i.e. 2.00, 1.75, 1.50 and 1.25 mm.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
RAYLEIGH = 0.265          # the classical dip; not tuned to our data
MTF_MIN = 0.50            # Digit 360's bar, arXiv:2411.02479. D >= 0.667.
# A dip can only mean something if there is an impression to put a dip in. The
# reconstruction work of 2026-09-05 measured this sensor family's response as
# 28 grey levels over 0.548 mm, so one grey level is 0.0196 mm of impression.
# The depth zero itself is uncertain by about 0.03 mm on these low-area probes,
# and claiming to resolve two features from an impression shallower than the
# uncertainty in where the surface was is not a measurement. 2.5 levels is
# 0.049 mm, the first depth that clears it.
MIN_PEAK = 2.5            # grey levels
NOISE_K = 3.0             # dip must exceed this many times its own scatter
BAND_MM = 0.40            # half-width of the strip averaged across the axis
ELEMENT_MM = 1.0


# Runs whose scale must never be used: the unit in the holder was not the one
# named, so the optics measured belong to a different sensor.
WRONG_UNIT = ("__WRONG_SENSOR", "__UNVERIFIED")

# Runs set aside for a measurement problem. These are excluded from being READ
# as profiles, but their SCALE still counts -- a bad zero or a different settle
# time says nothing about the camera's millimetres per pixel, which is what a
# scale is, and each scale carries its own `scale_trusted` self-check anyway.
SET_ASIDE = ("__badzero", "__settle015", "__failed", "__overpressed",
             "__noisyzero", "__read06")


def _state_files():
    """Every run's state.json, wherever it is filed.

    `data/_discarded/` holds runs moved out of the dataset on 2026-09-07. They
    are one directory deeper, so the two globs below used to miss them -- and
    that turned out to matter: four of them carry trusted scales, and dropping
    them moved the median scale 4.9 %, which moved the dip of every unit that
    has no scale of its own. An analysis whose numbers change when unused data
    is tidied into a different folder is reading the folder layout, so both
    trees are scanned and the result is the same either way.
    """
    import glob
    return sorted(glob.glob(str(ROOT / "data" / "*" / "*" / "state.json"))
                  + glob.glob(str(ROOT / "data" / "*" / "*" / "*" / "state.json"))
                  + glob.glob(str(ROOT / "data" / "_discarded" / "*" / "*" / "*"
                                  / "state.json")))


def _J_from(sc):
    for v in (sc or {}).values():
        if not isinstance(v, dict):
            continue
        if all(k in v for k in ("px_per_mm_xx", "px_per_mm_xy",
                                "px_per_mm_yx", "px_per_mm_yy")):
            if not v.get("scale_trusted", True):
                continue
            return np.array([[v["px_per_mm_xx"], v["px_per_mm_yx"]],
                             [v["px_per_mm_xy"], v["px_per_mm_yy"]]], float)
    return None


def jacobian(state, sensor=None):
    """Pixels per mm for this unit.

    The pair passes skip the scale phase -- it presses the probe at ten lateral
    offsets, which is a lot of stress for two 1 mm posts, and the scale belongs
    to the sensor's OPTICS, not to the probe in use. So fall back to the same
    unit's scale from a pass that did measure one, and take only a measurement
    that passed its own self-check.
    """
    J = _J_from(state.get("scale"))
    if J is not None or sensor is None:
        return J
    # A unit can have a trusted scale in more than one pass, and taking
    # whichever came first alphabetically made the answer depend on the pass
    # NAME: 9DTact_medium_2mm_r2 drew its scale from a run set aside as
    # __settle015 only because "ball4" sorts before "cube4", and its dip moved
    # by up to 0.17 when that directory was filed elsewhere. Runs that were
    # kept are preferred over runs that were set aside, and the set-aside ones
    # are still there as a fallback for a unit that has nothing else.
    kept, aside = [], []
    for p in _state_files():
        raw = Path(p).parent.name
        if any(r in raw for r in WRONG_UNIT):
            continue
        name = raw
        for suf in ("__2", "__3", "__4") + SET_ASIDE:
            name = name.replace(suf, "")
        if name != sensor:
            continue
        (aside if any(r in raw for r in SET_ASIDE) else kept).append(p)
    for p in kept + aside:
        try:
            J = _J_from(json.loads(Path(p).read_text()).get("scale"))
        except Exception:
            continue
        if J is not None:
            where = Path(p).parent.parent.name
            if p in aside:
                where += f" ({Path(p).parent.name} — set aside; no kept run has a scale)"
            print(f"  scale borrowed from {where}")
            return J
    # Five units never produced a scale that passed its own self-check, and the
    # pair passes cannot measure one (the scale phase presses at ten offsets,
    # which is what two 1 mm posts must not do). Fall back to the median of
    # every trusted scale so the dip can still be computed -- but say so: units
    # differ by about 15 % (measured 2026-09-06), and that is the error on this
    # analysis's mm axis. It stretches the axis; it does not invent a dip.
    Js = []
    for p in _state_files():
        if any(r in Path(p).parent.name for r in WRONG_UNIT):
            continue
        try:
            Jx = _J_from(json.loads(Path(p).read_text()).get("scale"))
        except Exception:
            continue
        if Jx is not None:
            Js.append(Jx)
    if Js:
        med = np.median(np.stack(Js), axis=0)
        print(f"  !! no trusted scale for this unit — using the median of "
              f"{len(Js)} others. The mm axis is provisional, +-15 %.")
        return med
    return None


def isotropic(img, J, centre, out=(700, 700)):
    """Square, axis-aligned pixels, centred on the contact."""
    ppm = float(np.sqrt(abs(np.linalg.det(J))))
    A = ppm * np.linalg.inv(J)
    h, w = out
    M = np.zeros((2, 3))
    M[:, :2] = A
    M[:, 2] = np.array([w / 2.0, h / 2.0]) - A @ np.asarray(centre, float)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE), ppm


def blob_centre(diff, level=4):
    m = (diff >= level).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return None
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return float(cen[k][0]), float(cen[k][1])


def axis_and_profile(d, ppm):
    """Major axis of the darkening, and the profile along it."""
    w = np.clip(d - 4.0, 0, None)
    if w.sum() <= 0:
        return None
    yy, xx = np.mgrid[0:d.shape[0], 0:d.shape[1]]
    t = w.sum()
    cx, cy = (w * xx).sum() / t, (w * yy).sum() / t
    vxx = (w * (xx - cx) ** 2).sum() / t
    vyy = (w * (yy - cy) ** 2).sum() / t
    vxy = (w * (xx - cx) * (yy - cy)).sum() / t
    ev, evec = np.linalg.eigh(np.array([[vxx, vxy], [vxy, vyy]]))
    u = evec[:, 1]                      # major axis: along the pair
    v = np.array([-u[1], u[0]])         # across it
    s = ((xx - cx) * u[0] + (yy - cy) * u[1]) / ppm      # mm along
    r = ((xx - cx) * v[0] + (yy - cy) * v[1]) / ppm      # mm across
    keep = np.abs(r) <= BAND_MM
    lo, hi = -3.0, 3.0
    edges = np.arange(lo, hi + 0.02, 0.02)
    idx = np.digitize(s[keep], edges) - 1
    vals = d[keep]
    prof = np.full(len(edges) - 1, np.nan)
    for i in range(len(edges) - 1):
        sel = idx == i
        if sel.sum() > 8:
            prof[i] = vals[sel].mean()
    return 0.5 * (edges[:-1] + edges[1:]), prof, np.degrees(np.arctan2(u[1], u[0]))


def profile_noise(ps):
    """Per-sample noise of the profile, from its own high-frequency content.

    The successive-difference estimator: for a signal that is smooth on the
    scale of one sample, diff() is almost pure noise, and the median absolute
    difference is robust to the peaks and the trough themselves. The sqrt(2)
    undoes differencing two noisy samples; 0.6745 converts a MAD to a sigma.
    """
    d = np.diff(ps)
    if d.size < 8:
        return np.nan
    return float(np.median(np.abs(d)) / 0.6745 / np.sqrt(2.0))


def dip_fraction(x, prof, sep_mm):
    """1 - trough/mean(peaks), with the peaks sought near the known centres.

    Also returns the noise this particular profile can support, because with
    one pass over the ladder there is no scatter across passes to gate on.
    Note the estimator uses max in the peak windows and min in the trough one:
    extrema are biased BY noise, upward and downward respectively, so noise
    inflates the dip and can manufacture a separation. That is what the gate is
    sized against.
    """
    good = np.isfinite(prof)
    if good.sum() < 20:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    xs, ps = x[good], prof[good]
    half = sep_mm / 2.0
    out = []
    for c in (-half, +half):
        m = np.abs(xs - c) <= 0.35
        out.append(ps[m].max() if m.any() else np.nan)
    mid = np.abs(xs) <= 0.20
    trough = ps[mid].min() if mid.any() else np.nan
    # Judge on the WEAKER of the two posts, not on their mean. The two do not
    # press equally: measured 2026-09-07, the weak/strong ratio runs 0.86-0.96
    # on units whose gel is square to the probe and 0.45-0.68 on units where it
    # is not, and 9DTact_medium_1mm_r2 sat at 0.45 under both pair probes, so
    # it is the SENSOR's seating, not the probe. Averaging two unequal peaks
    # produces a number that describes neither: a strong post can carry the
    # mean while the weak one is invisible, and the trough then looks deep
    # against it. Two features are resolved only if the weaker one is itself a
    # feature -- so the dip is measured against min(P1, P2) and the signal floor
    # applies to it too. This makes the test STRICTER, not looser: min <= mean,
    # so every dip falls and every peak is harder to clear.
    peak = float(np.nanmin(out))
    peak_mean = float(np.nanmean(out))
    sym = (float(np.nanmin(out) / np.nanmax(out))
           if np.nanmax(out) > 0 else np.nan)
    if not np.isfinite(peak) or peak <= 0 or not np.isfinite(trough):
        return np.nan, peak, np.nan, np.nan, np.nan
    dip = float(1.0 - trough / peak)
    # Michelson contrast, which is what Digit 360 calls MTF for this test.
    mtf = float((peak - trough) / (peak + trough)) if (peak + trough) > 0 else np.nan
    # Propagate the profile noise into the dip. peak is the mean of two
    # maxima, so its noise is sigma/sqrt(2); the trough is a single minimum.
    sig = profile_noise(ps)
    if np.isfinite(sig):
        sd = float(np.hypot(sig / peak,
                            trough * sig / (np.sqrt(2.0) * peak ** 2)))
    else:
        sd = np.nan
    return dip, float(peak), sd, mtf, sym


def main():
    dataset, sensor = sys.argv[1], sys.argv[2]
    probes = sys.argv[3:] or ["pair100", "pair075", "pair050", "pair025"]
    cfg = yaml.safe_load(open(ROOT / "config" / "probes.yaml"))
    gaps = {p["id"]: p["gap_mm"] for p in cfg["probes"] if p["tip"] == "cylinder_pair"}
    print(f"  {sensor}   Rayleigh dip >= {RAYLEIGH:.3f}, "
          f"and > {NOISE_K:.0f}x the noise of its own profile;\n"
          f"  Digit 360 (arXiv:2411.02479) instead asks MTF >= {MTF_MIN:.2f}, "
          f"which is the same as a dip of {2*MTF_MIN/(1+MTF_MIN):.3f}\n")
    for probe in probes:
        # A re-run lands in `<sensor>__2`, `__3` and so on, and a discarded
        # attempt keeps a descriptive suffix. Take the NEWEST directory whose
        # name is this sensor once the suffixes are stripped, and never one
        # that was explicitly set aside.
        REJECT = SET_ASIDE + WRONG_UNIT
        cands = []
        droot = ROOT / "data" / dataset
        if not droot.exists():
            hits = [d for d in (ROOT / "data").glob(f"*/{dataset}") if d.is_dir()]
            if hits:
                droot = hits[0]
        for c in droot.glob(f"{sensor}*"):
            if not c.is_dir() or any(r in c.name for r in REJECT):
                continue
            base = c.name
            for suf in ("__2", "__3", "__4"):
                base = base.replace(suf, "")
            if base == sensor and (c / f"shape_{probe}" / "ladder.csv").exists():
                cands.append(c)
        if not cands:
            print(f"  {probe}: 데이터 없음")
            continue
        run = max(cands, key=lambda c: c.stat().st_mtime)
        if run.name != sensor:
            print(f"  using {run.name}")
        d = run / f"shape_{probe}"
        if not d.exists():
            print(f"  {probe}: 데이터 없음")
            continue
        st = json.loads((run / "state.json").read_text())
        J = jacobian(st, sensor)
        if J is None:
            print(f"  {probe}: 이 센서에 축척 없음 -- --phase scale 먼저")
            continue
        sep = ELEMENT_MM + gaps[probe]
        ref = cv2.cvtColor(cv2.imread(str(run / "reference.png")), cv2.COLOR_BGR2GRAY)
        lad = pd.read_csv(d / "ladder.csv")
        print(f"  {probe}  중심간격 {sep:.2f} mm")
        print(f"    {'depth':>7}{'dip':>9}{'sd':>8}{'weak':>8}{'sym':>7}  "
              f"{'Rayleigh':<9}{'MTF':>8}  {'D360':<9}{'lp/mm':>7}")
        for dep, grp in lad.groupby(lad.target_depth_mm):
            dips = []
            for _, row in grp.iterrows():
                img = cv2.cvtColor(cv2.imread(str(d / row.file)), cv2.COLOR_BGR2GRAY)
                raw = np.clip(ref.astype(np.int32) - img.astype(np.int32), 0, 255).astype(np.uint8)
                c = blob_centre(raw)
                if c is None:
                    continue
                dw, ppm = isotropic(raw.astype(np.float32), J, c)
                got = axis_and_profile(dw, ppm)
                if got is None:
                    continue
                x, prof, _ = got
                f, peak, sd1, m, sy = dip_fraction(x, prof, sep)
                if np.isfinite(f):
                    dips.append((f, peak, sd1, m, sy))
            if not dips:
                print(f"    {dep:>7.2f}{'접촉 없음':>26}")
                continue
            fs = np.array([q[0] for q in dips])
            pk = np.mean([q[1] for q in dips])
            # The ladder used to be walked three times and the scatter across
            # those passes was the noise. --shape-repeats is 1 now, so that
            # scatter does not exist, and the old code let sd = nan pass the
            # gate unconditionally -- a single noisy dip counted as resolved.
            # Use each profile's OWN noise instead, and keep the across-image
            # scatter as well when there happens to be more than one image;
            # take whichever is larger, since either kind of variation is real.
            mtf = float(np.nanmean([q[3] for q in dips]))
            sym = float(np.nanmean([q[4] for q in dips]))
            own = np.nanmean([q[2] for q in dips])
            across = fs.std(ddof=1) / np.sqrt(len(fs)) if len(fs) > 1 else np.nan
            sd = np.nanmax([own, across]) if np.isfinite(own) or np.isfinite(across) else np.nan
            # No noise estimate at all means the dip cannot be defended, so it
            # does not count. Failing closed is the whole point of a gate.
            weak = not np.isfinite(pk) or pk < MIN_PEAK
            ok = (not weak and fs.mean() >= RAYLEIGH and np.isfinite(sd)
                  and fs.mean() > NOISE_K * sd)
            why = ("신호부족" if weak else
                   "분해" if ok else
                   "잡음" if fs.mean() >= RAYLEIGH else "미분해")
            ok_mtf = (not weak and np.isfinite(mtf) and mtf >= MTF_MIN
                      and np.isfinite(sd) and fs.mean() > NOISE_K * sd)
            lp = 0.5 / sep          # line pairs per mm at this spacing
            print(f"    {dep:>7.2f}{fs.mean():>9.3f}{sd:>8.3f}{pk:>8.2f}{sym:>7.2f}  "
                  f"{why:<9}{mtf:>8.3f}  "
                  f"{('분해' if ok_mtf else ('신호부족' if weak else '미분해')):<9}{lp:>7.2f}")
        print()


if __name__ == "__main__":
    main()
