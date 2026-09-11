#!/usr/bin/env python3
"""Shape reconstruction, 9DTact's way, on every unit of the Pass A dataset.

    analyse_shape.py                      # all 9DTact units
    analyse_shape.py 9DTact_soft_2mm_r1   # one, with the per-rung tables

THE METHOD (their shape_reconstruction/_2_Sensor_Calibration.py, sensor.py)
------------------------------------------------------------------------
  calibrate    press a ball of known radius R; inside the contact the sphere's
               own geometry gives the true height at every pixel,
                   h(r) = sqrt(R^2 - r^2) - sqrt(R^2 - rc^2),
               and pairing that with each pixel's darkening (reference minus
               frame) builds a lookup GREY -> DEPTH, one mean per grey level.
  reconstruct  depth = lookup[blur(reference - frame)], minus the lookup at
               the lighting threshold, then smoothed.

THREE THINGS DONE DIFFERENTLY, EACH FORCED BY THIS RIG AND EACH MEASURED
-----------------------------------------------------------------------
* The pixels are not square. 9DTact rectifies with a checkerboard and carries
  one mm-per-pixel; a checkerboard cannot go inside a sealed sensor, so the
  scale was measured by moving the robot a known distance and tracking the
  imprint. That gives a full 2x2 Jacobian (about 1.06-1.28 anisotropy, rotated
  25-33 deg), and every frame is resampled through its inverse onto square,
  axis-aligned pixels before anything else happens.

* The contact radius is COMPUTED, not detected. A hand-held press does not say
  how deep it went, so 9DTact must threshold the imprint to find the circle.
  Here the robot measures the depth d, and the radius follows from geometry,
  sqrt(2Rd - d^2). The thresholded region over-reads the true contact by a
  constant 1.25x beyond 0.18 mm (measured 2026-09-05), so following the paper
  exactly would build the height map on a radius 25 % wrong.

* The calibration depths are corrected for the sphere's zero bias. The ball's
  own fitted surface sits 0.155 +- 0.029 mm too deep (docs/hertz_zero_bias.md,
  17 units), so the ladder's recorded depths under-read the true ones by that
  much and a lookup built on them reads every reconstruction shallow by the
  same amount. This is the "0.128 mm constant bias" the 2026-09-05 pilot saw
  and could not explain. Each unit's own offset -- its flat-punch zero minus
  its ball zero, both measured -- is added to the ball ladder's depths before
  the lookup is built; both the raw and the corrected results are reported.

SCORING
-------
On probes whose imprint has no free parameters: cyl4, a flat disc of radius
2.00 mm, and cube4, a flat square of edge 4.00 mm, each pressed to a
robot-measured depth. The reconstruction is asked for the depth at the centre,
the size of the imprint at half depth, and the flatness of the floor.

The depth RESOLUTION of each unit is read off its own calibration: the
darkest grey level the deepest ball press reaches, divided into the depth it
carries. It is what limits the residual, and comparing it across designs is
what test 2 is for.
"""
from __future__ import annotations

import importlib.util
import io
import json
import contextlib
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("ar", ROOT / "scripts" / "analyse_resolution.py")
ar = importlib.util.module_from_spec(_spec)
sys.modules["ar"] = ar
_spec.loader.exec_module(ar)

LIGHTING_THRESHOLD = 2          # 9DTact's
KERNELS = (7, 7)                # 9DTact's
BALL_R = 2.0                    # ball4
CYL_R = 2.0                     # cyl4
CUBE_EDGE = 4.0                 # cube4
OUT = (900, 900)
# Input downscale factor. 1 = the camera's own 1920x1080. Set by
# analyse_shape_resolution.py to ask how much resolution the method actually
# needs: every frame (reference included) is shrunk by this factor with area
# averaging before anything else runs, and the Jacobian shrinks with it, so the
# rest of the pipeline sees a camera with fewer, larger pixels and nothing else
# changes.
DOWNSCALE = 1
# Separate factors for x and y, so a target size can hold 16:9 exactly where
# a single factor would round it away (e.g. 48x27 needs 40.0 in x and 40.0
# in y; 8x5 needs 240 and 216). DOWNSCALE stays as their geometric mean for
# the scale-aware thresholds.
DOWNSCALE_XY = (1.0, 1.0)


def set_downscale(width, height, w0=1920, h0=1080):
    """Ask for an exact output size; everything scale-aware follows."""
    global DOWNSCALE, DOWNSCALE_XY
    fx, fy = w0 / width, h0 / height
    DOWNSCALE_XY = (fx, fy)
    DOWNSCALE = float(np.sqrt(fx * fy))
DATASETS = {"ball4": "20260905_passA_ball4", "cube4": "20260905_passA_cube4",
            "cyl4": "20260905_passA_cyl4"}


# ---------------------------------------------------------------- geometry --
def isotropic(img, J, centre):
    return ar.isotropic(img.astype(np.float32), J, centre, out=OUT)


def contact_circle(diff, gray_thresh=3):
    mask = (diff > gray_thresh).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 300 / (DOWNSCALE ** 2):
        return None
    (x, y), r = cv2.minEnclosingCircle(c)
    return float(x), float(y), float(r)


def sphere_pairs(diff, mm_per_px, R, rc_mm):
    """(grey, true height) for every pixel inside the geometric contact."""
    h, w = diff.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r_mm = np.hypot(xx - w / 2.0, yy - h / 2.0) * mm_per_px
    if rc_mm <= 0 or rc_mm >= R:
        return None, None
    inside = r_mm < rc_mm
    hm = np.sqrt(np.maximum(R ** 2 - r_mm[inside] ** 2, 0)) - np.sqrt(R ** 2 - rc_mm ** 2)
    return diff[inside], hm


def build_lookup(greys, depths):
    g = np.clip(np.concatenate(greys).astype(int), 0, None)
    d = np.concatenate(depths).astype(float)
    top = int(g.max())
    lut = np.zeros(top + 1); n = np.zeros(top + 1, dtype=int)
    for lv in range(top + 1):
        m = g == lv
        if m.any():
            lut[lv] = d[m].mean(); n[lv] = int(m.sum())
    seen = np.flatnonzero(n > 0)
    if len(seen) > 1:
        lut = np.interp(np.arange(top + 1), seen, lut[seen])
    return lut, n


def reconstruct(ref_w, img_w, lut):
    diff = ref_w.astype(np.int32) - img_w.astype(np.int32) - LIGHTING_THRESHOLD
    diff = np.where(diff < 100, diff, 0) + LIGHTING_THRESHOLD
    diff = np.clip(diff, 0, len(lut) - 1)
    diff = cv2.GaussianBlur(diff.astype(np.float32), (7, 7), 0)
    depth = lut[np.clip(diff.astype(int), 0, len(lut) - 1)] - lut[LIGHTING_THRESHOLD]
    for k in KERNELS:
        depth = cv2.GaussianBlur(depth.astype(np.float32), (k, k), 0)
    return depth


# ------------------------------------------------------------------- loading --
def _shrink(g):
    if DOWNSCALE == 1:
        return g
    h, w = g.shape
    fx, fy = DOWNSCALE_XY
    return cv2.resize(g, (max(1, int(round(w / fx))), max(1, int(round(h / fy)))),
                      interpolation=cv2.INTER_AREA)


def load_run(probe, sensor):
    run = ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact" / DATASETS[probe] / sensor
    st = json.loads((run / "state.json").read_text())
    lad = pd.read_csv(run / f"shape_{probe}" / "ladder.csv")
    ref = cv2.cvtColor(cv2.imread(str(run / "reference.png")), cv2.COLOR_BGR2GRAY)
    return run, st, lad, _shrink(ref)


def gray(run, probe, f):
    return _shrink(cv2.cvtColor(cv2.imread(str(run / f"shape_{probe}" / f)), cv2.COLOR_BGR2GRAY))


def zero_surface(st):
    z = st.get("zero") or {}
    return float(z["surface_mm"]) if z.get("surface_mm") is not None else None


def deepest_centre(run, probe, lad, ref):
    """Where the contact is in the image, from the deepest frame.

    Always found at the camera's FULL resolution and then scaled by DOWNSCALE.
    The resolution sweep asks whether the shape can be reconstructed with
    fewer pixels, not whether the contact can be located with fewer pixels --
    and the locator (threshold, 5x5 opening, 11x11 closing, in PIXELS) fails
    first: at 30x16 the 4 mm imprint is five pixels wide and the closing
    kernel is larger than the imprint, so the mask vanishes and the run was
    reported as "no contact" while the reconstruction itself had never been
    tried. Found once at full resolution, the centre is the same physical
    point at every scale and the sweep measures the reconstruction alone.
    """
    deep = lad.sort_values("depth_mm").iloc[-1]
    full_ref = cv2.cvtColor(cv2.imread(str(run / "reference.png")), cv2.COLOR_BGR2GRAY)
    full_img = cv2.cvtColor(cv2.imread(str(run / f"shape_{probe}" / deep["file"])), cv2.COLOR_BGR2GRAY)
    d = np.clip(full_ref.astype(np.int32) - full_img.astype(np.int32), 0, 255)
    saved, saved_xy = globals()["DOWNSCALE"], globals()["DOWNSCALE_XY"]
    globals()["DOWNSCALE"] = 1             # contact_circle's area floor is scale-aware
    try:
        c = contact_circle(d.astype(np.uint8))
    finally:
        globals()["DOWNSCALE"] = saved
    if c is None:
        return None
    fx, fy = saved_xy
    return (c[0] / fx, c[1] / fy, c[2] / saved)


# ------------------------------------------------------------ evaluation --
def imprint_size(depth, mm_per_px, d_centre, axis):
    """Full width at half the centre depth along one axis through the centre."""
    h, w = depth.shape
    prof = depth[h // 2, :] if axis == "x" else depth[:, w // 2]
    half = d_centre / 2.0
    c = len(prof) // 2
    above = prof >= half
    if not above[c]:
        return np.nan
    lo = c
    while lo > 0 and above[lo - 1]:
        lo -= 1
    hi = c
    while hi < len(prof) - 1 and above[hi + 1]:
        hi += 1
    return (hi - lo + 1) * mm_per_px


def imprint_geometry(depth, mm_per_px, d_centre):
    """Size and orientation of the imprint from its half-depth contour.

    Rotation-invariant on purpose. The first version measured the width along
    the image x and y axes through the centre, which is right for a disc and
    wrong for a square: cube4 sits in its holder at whatever angle it was
    pushed in, and a square rotated by theta is wider along x by 1/cos(theta)
    -- the +0.46 mm median "edge error" reported on 2026-09-07 was mostly
    that angle, not the reconstruction. The minimum-area rectangle around the
    half-depth contour gives the two edge lengths whatever the angle, and its
    angle is recorded so the true shape can be drawn where the probe actually
    was.

    Returns (edge_long, edge_short, angle_deg, equivalent_diameter) in mm/deg,
    or NaNs if there is no usable contour.
    """
    m = (depth >= d_centre / 2.0).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return np.nan, np.nan, np.nan, np.nan
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 20:
        return np.nan, np.nan, np.nan, np.nan
    (_, _), (w, h), ang = cv2.minAreaRect(c)
    w, h = w * mm_per_px, h * mm_per_px
    d_eq = 2.0 * np.sqrt(cv2.contourArea(c) / np.pi) * mm_per_px
    return max(w, h), min(w, h), float(ang), d_eq


def evaluate(run, probe, lad, ref, J, lut, mm_per_px, zero_shift):
    circ = deepest_centre(run, probe, lad, ref)
    if circ is None:
        return []
    centre = (circ[0], circ[1])
    ref_w, _ = isotropic(ref, J, centre)
    h, w = OUT
    yy, xx = np.mgrid[0:h, 0:w]
    r_mm = np.hypot(xx - w / 2.0, yy - h / 2.0) * mm_per_px
    rows = []
    for _, r in lad.iterrows():
        img_w, _ = isotropic(gray(run, probe, r["file"]), J, centre)
        dep = reconstruct(ref_w, img_w, lut)
        core = dep[r_mm < 0.5 * CYL_R]
        d_c = float(np.median(core)); flat = float(np.std(core))
        e_long, e_short, ang, d_eq = imprint_geometry(dep, mm_per_px, d_c)
        # disc: the equivalent-area diameter is the size; square: the two
        # edges of the fitted rectangle are, whatever its angle
        wx, wy = (d_eq, d_eq) if probe == "cyl4" else (e_long, e_short)
        rows.append(dict(probe=probe, repeat=int(r["repeat"]), target=float(r["target_depth_mm"]),
                         true=float(r["depth_mm"]), recon=d_c, flat=flat,
                         width_x=wx, width_y=wy, angle_deg=ang))
    return rows


def analyse(sensor, verbose=False):
    cal_run, cal_st, cal_lad, cal_ref = load_run("ball4", sensor)
    out = {"sensor": sensor.replace("9DTact_", "")}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        J = ar.jacobian(cal_st, sensor)
    src = buf.getvalue().strip().splitlines()
    out["scale_source"] = ("own" if not src else
                           "median" if "median" in src[-1] else "borrowed")
    if J is None:
        out["error"] = "no scale"; return out, []
    # fewer pixels per millimetre, by the x and y factors separately: J's
    # rows are image x and image y
    J = np.diag([1.0 / DOWNSCALE_XY[0], 1.0 / DOWNSCALE_XY[1]]) @ J
    ppm = float(np.sqrt(abs(np.linalg.det(J)))); mm_per_px = 1.0 / ppm
    out["downscale"] = DOWNSCALE
    out["px_per_mm"] = ppm

    # the sphere's zero bias for THIS unit, from its own flat-punch zero
    z_ball = zero_surface(cal_st)
    z_flat = None
    for probe in ("cyl4", "cube4"):
        try:
            z_flat = zero_surface(load_run(probe, sensor)[1])
            if z_flat is not None:
                break
        except Exception:  # noqa: BLE001
            continue
    shift = (z_flat - z_ball) if (z_ball is not None and z_flat is not None) else 0.155
    out["zero_shift_mm"] = shift
    out["zero_shift_source"] = "own" if (z_ball is not None and z_flat is not None) else "campaign mean"

    circ = deepest_centre(cal_run, "ball4", cal_lad, cal_ref)
    if circ is None:
        out["error"] = "no contact in the calibration frames"; return out, []
    centre = (circ[0], circ[1])
    ref_w, _ = isotropic(cal_ref, J, centre)

    results = {}
    for tag, corr in (("raw", 0.0), ("corrected", shift)):
        gs, ds = [], []
        max_grey = 0
        for _, r in cal_lad.iterrows():
            d = float(r["depth_mm"]) + corr
            if d <= 0:
                continue
            img_w, _ = isotropic(gray(cal_run, "ball4", r["file"]), J, centre)
            diff = np.clip(ref_w - img_w, 0, 255)
            rc = float(np.sqrt(max(2 * BALL_R * d - d * d, 0)))
            g, hm = sphere_pairs(diff, mm_per_px, BALL_R, rc)
            if g is None or not len(g):
                continue
            gs.append(g); ds.append(hm)
            max_grey = max(max_grey, int(np.percentile(g, 99)))
        if not gs:
            out["error"] = "no calibration pixels"; return out, []
        lut, n = build_lookup(gs, ds)
        results[tag] = (lut, n, max_grey)

    lut_raw, n_raw, mg = results["raw"]
    lut_c, _, _ = results["corrected"]
    if len(lut_c) <= LIGHTING_THRESHOLD + 1:
        # A lookup with no grey range: the contact is a pixel or two and the
        # calibration frames cannot separate depths. That is the genuine end
        # of the method at this resolution, and it is reported as such.
        out["error"] = f"lookup spans only {len(lut_c)} grey levels"
        out["grey_levels_used"] = mg
        return out, []
    deepest = float(cal_lad.depth_mm.max()) + shift
    out["grey_levels_used"] = mg
    out["mm_per_grey_level"] = deepest / max(mg, 1)
    out["ball_deepest_mm"] = deepest

    rows = []
    for probe in ("cyl4", "cube4"):
        try:
            run, st, lad, ref = load_run(probe, sensor)
        except Exception as exc:  # noqa: BLE001
            continue
        for tag, lut in (("raw", lut_raw), ("corrected", lut_c)):
            for rr in evaluate(run, probe, lad, ref, J, lut, mm_per_px, shift):
                rr["lut"] = tag; rr["sensor"] = out["sensor"]; rows.append(rr)

    df = pd.DataFrame(rows)
    for probe, size_true in (("cyl4", 2 * CYL_R), ("cube4", CUBE_EDGE)):
        for tag in ("raw", "corrected"):
            s = df[(df.probe == probe) & (df.lut == tag)]
            if s.empty:
                continue
            err = s["recon"] - s["true"]
            k = f"{probe}_{tag}"
            out[f"{k}_bias"] = float(err.mean())
            out[f"{k}_mae"] = float(err.abs().mean())
            # The two shallowest rungs sit at or under the lighting threshold
            # the method subtracts, so they read low by construction; the
            # imprint is not fully developed there either. Judge depth and
            # size on the rungs from 0.3 mm, and say so.
            deep = s[s["true"] >= 0.25]
            if len(deep):
                e2 = deep["recon"] - deep["true"]
                out[f"{k}_bias_deep"] = float(e2.mean())
                out[f"{k}_mae_deep"] = float(e2.abs().mean())
            # one linear correction, as in the pilot, then the residual
            if len(s) >= 3:
                a, b = np.polyfit(s["true"], s["recon"], 1)
                out[f"{k}_slope"] = float(a)
                out[f"{k}_rms_after_linear"] = float(np.sqrt(np.mean((s["recon"] - (a * s["true"] + b)) ** 2)))
            dd = s[s["true"] >= 0.35] if (s["true"] >= 0.35).any() else s
            wv = np.r_[dd["width_x"].values, dd["width_y"].values]
            wmean = float(np.nanmean(wv)) if np.isfinite(wv).any() else np.nan
            out[f"{k}_size"] = float(wmean)
            out[f"{k}_size_err"] = float(wmean - size_true)
            out[f"{k}_flat"] = float(dd["flat"].mean())
            if probe == "cube4":
                # short / long of the fitted rectangle: 1.00 is square,
                # independent of how the cube sat in the holder
                q = (dd["width_y"] / dd["width_x"]).values
                out[f"{k}_squareness"] = float(np.nanmean(q)) if np.isfinite(q).any() else np.nan
                out[f"{k}_angle_deg"] = (float(np.nanmedian(dd["angle_deg"]))
                                         if np.isfinite(dd["angle_deg"]).any() else np.nan)
    if verbose:
        print(f"\n{sensor}: {ppm:.1f} px/mm ({out['scale_source']}), zero shift "
              f"{shift:+.3f} mm ({out['zero_shift_source']}), {mg} grey levels over "
              f"{deepest:.3f} mm = {out['mm_per_grey_level']*1000:.1f} um/level")
        for probe in ("cyl4", "cube4"):
            s = df[(df.probe == probe) & (df.lut == "corrected")]
            if s.empty:
                continue
            print(f"\n  {probe} (corrected lookup)")
            print(f"  {'target':>7} {'true':>7} {'recon':>7} {'err':>7} {'width_x':>8} {'width_y':>8} {'flat':>6}")
            for _, r in s.iterrows():
                print(f"  {r["target"]:7.2f} {r["true"]:7.3f} {r["recon"]:7.3f} {r["recon"]-r["true"]:+7.3f} "
                      f"{r["width_x"]:8.2f} {r["width_y"]:8.2f} {r["flat"]:6.3f}")
    return out, rows


def main():
    reg = yaml.safe_load(open(ROOT / "config" / "sensor_registry.yaml"))
    if len(sys.argv) > 1:
        sensors = sys.argv[1:]
    else:
        sensors = [e["id"] for e in reg["sensors"] if e["id"].startswith("9DTact")
                   and e.get("gel_model") and e["id"] != "9DTact_medium_2mm_r1"]
    summ, rungs = [], []
    for s in sorted(sensors):
        try:
            o, r = analyse(s, verbose=len(sys.argv) > 1)
        except Exception as exc:  # noqa: BLE001
            o, r = {"sensor": s.replace("9DTact_", ""), "error": f"{type(exc).__name__}: {exc}"}, []
        summ.append(o); rungs += r
        if "error" in o:
            print(f"  {o['sensor']}: {o['error']}")
    S = pd.DataFrame(summ); R = pd.DataFrame(rungs)
    outdir = ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact"
    S.to_csv(outdir / "shape_reconstruction.csv", index=False)
    R.to_csv(outdir / "shape_reconstruction_rungs.csv", index=False)
    cols = ["sensor", "scale_source", "mm_per_grey_level", "grey_levels_used",
            "zero_shift_mm", "cyl4_raw_bias", "cyl4_corrected_bias", "cyl4_corrected_mae",
            "cyl4_corrected_bias_deep", "cyl4_corrected_rms_after_linear", "cyl4_corrected_size_err",
            "cube4_corrected_bias", "cube4_corrected_size_err", "cube4_corrected_squareness"]
    cols = [c for c in cols if c in S.columns]
    pd.set_option("display.width", 200)
    print("\n" + S[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"\n  -> {outdir/'shape_reconstruction.csv'}  ({len(S)} units)"
          f"\n  -> {outdir/'shape_reconstruction_rungs.csv'}  ({len(R)} rungs)")


if __name__ == "__main__":
    main()
