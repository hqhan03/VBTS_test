#!/usr/bin/env python3
"""Force estimation from the image, per unit, at a ladder of camera resolutions.

    force_vs_resolution.py                     # every unit, every size
    force_vs_resolution.py 9DTact_hard_2mm_r1  # one unit
    force_vs_resolution.py --sizes 1920x1080,320x180 --epochs 10   # a quick pass

WHAT IS ASKED
-------------
Test 1 collected 1000 labelled frames per unit: an image and the wrench measured
over that frame's own exposure window. This asks how much of the CAMERA is
needed to read the force back out -- the same question `shape_vs_resolution.md`
asks of shape reconstruction, on the same twelve 16:9 sizes so the two curves
can be laid side by side.

9DTACT'S PIPELINE, TAKEN AS IT IS
---------------------------------
Preprocessing is their `Sensor.raw_image_2_representation`
(`shape_reconstruction/sensor.py`), which is what `_1_Force_Estimation.py`
feeds the estimator. Three channels, built from the grey reference and the
grey frame:

    diff_darker   = ref - img, negatives clipped to 0
    diff_brighter = img - ref, negatives clipped to 0
    channel 0 = ref            (the reference itself, unscaled)
    channel 1 = diff_brighter * 3
    channel 2 = diff_darker * 3

with `scale = 3` as in their source, values kept as 0-255 uint8. Their
`lighting_threshold` (2) belongs to the shape path, not this one, and is not
applied here either.

The model and its training are theirs as well (`force_estimation/train.py`,
`model/cnn.py`, `force_config.yaml`):

  * ResNet-18, ImageNet-pretrained, final fc replaced by a 6-output linear
    layer -- the full wrench, which this rig measures too.
  * Pixel values fed as 0-255 floats, unnormalised, as in `dtact_dataset.py`.
  * L1 loss with `reduction='sum'`, Adam at 5e-4, a linear decay, batch 64.
  * Labels min-max scaled to [0, 1] over the training set, which is what
    their `*_norm.npy` wrenches and the `force[force<0]=0; force[force>1]=1`
    clamp in `estimator.py` imply. Errors are converted back to newtons.

Three departures, each forced by the question being asked and none of them a
change to the method. Their images are a fixed 345x460 crop; here the size is
the independent variable, so the batch is reduced at the large end to fit the
card. They train 200 epochs on one sensor; 17 units x 12 sizes at 200 epochs
is days, so the epoch count is a flag and the value used is written into the
CSV. And their crop is a rectified 345x460 region of a 640x480 camera, while
this rig's frames are the full 1920x1080 -- rectification needs a checkerboard
inside a sealed sensor, which is why this campaign measures the scale with the
robot instead (see `contact_variable.md`).

ResNet-18 runs at every size in the ladder: its five stride-2 stages take
8x5 down to 1x1, which the adaptive pool accepts. Nothing about the network
changes between sizes.

THE SPLIT
---------
Held out by CYCLE, not at random. Neighbouring frames of one press are nearly
the same picture at nearly the same force, so a random split scores a model on
data it has effectively seen and reports an error several times too small. The
last 30 % of the loading cycles and the last 30 % of the shear cycles are the
test set; everything earlier is training.

WHAT IS REPORTED
----------------
MAE in newtons on the held-out cycles, for Fz and for the lateral magnitude,
against the MAE of predicting the training mean. A model that cannot beat that
baseline has learnt nothing, which is the expected answer at the small end.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "9DTact" / "20260907_passB_ball8"
SIZES = [(1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240),
         (320, 180), (160, 90), (80, 45), (48, 27), (32, 18), (16, 9), (8, 5)]


# ------------------------------------------------------------------ data --
REP_SCALE = 3          # sensor.py: scale = 3
AXES = ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")


# ---------------------------------------------------------- marker handling --
# What the literature does with a MARKER sensor, and why this file now offers it.
#
# Marker Displacement Methods are the standard reading of a marker gel: track
# the dots between the resting frame and the loaded one, and the local
# displacement gives the force, because the dot field measures the elastomer's
# deformation directly rather than through its shading. GelSlim goes further and
# runs inverse FEM on those displacements. The known cost, stated in the same
# literature, is that opaque dots OCCLUDE the geometry the shading would show.
#
# Both of those are testable here, and this campaign has a reason to doubt the
# first: cross_principle.md 3.5 measured 1.24 dots inside a 2 N contact, so the
# displacement "field" is about one vector. So two representations:
#
#   inpaint  the dots are masked out of the difference image and filled from
#            their surroundings, which is the occlusion cost removed and
#            nothing else added.
#   flow     dense optical flow from the reference to the frame, which is the
#            displacement method in the form a CNN can eat, plus the difference
#            magnitude as the third channel.
#
# Both return the same uint8 HxWx3 contract as the other representations, so
# the sweep, the shrink and the training are untouched.
DOT_AREA = (1500, 60000)          # px^2 at full resolution; a dot is ~9500


def dot_mask(ref_bgr, grow=9):
    """Where the opaque dots are, from the resting frame."""
    from scipy import ndimage
    g = (cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY) if ref_bgr.ndim == 3
         else ref_bgr).astype(np.float32)
    hp = cv2.GaussianBlur(g, (0, 0), 25) - g
    thr = hp > max(4.0, np.percentile(hp, 99.0) * 0.35)
    lab, n = ndimage.label(thr)
    if n == 0:
        return np.zeros(g.shape, bool)
    areas = ndimage.sum(thr, lab, range(1, n + 1))
    keep = [i + 1 for i, a in enumerate(areas) if DOT_AREA[0] <= a <= DOT_AREA[1]]
    m = np.isin(lab, keep).astype(np.uint8)
    if grow:
        m = cv2.dilate(m, np.ones((grow, grow), np.uint8))
    return m.astype(bool)


def _fill_masked(d, m, k=61):
    """Normalised box filter: each masked pixel takes the mean of the unmasked
    ones around it. cv2.inpaint would be nicer and is 20x too slow for 18000
    frames a unit."""
    keep = (~m).astype(np.float32)
    num = cv2.blur(d * keep, (k, k))
    den = cv2.blur(keep, (k, k)) + 1e-6
    out = d.copy()
    out[m] = (num / den)[m]
    return out


def marker_representation(ref_bgr, img_bgr, mask, mode):
    """`inpaint` or `flow`, both uint8 HxWx3."""
    r = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) if ref_bgr.ndim == 3 else ref_bgr.astype(np.float32)
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) if img_bgr.ndim == 3 else img_bgr.astype(np.float32)
    if mode == "inpaint":
        d = g - r
        if mask is not None and mask.any():
            d = _fill_masked(d, mask)
        out = np.zeros(r.shape + (3,), np.uint8)
        out[:, :, 0] = np.clip(r, 0, 255).astype(np.uint8)
        out[:, :, 1] = np.clip(np.clip(d, 0, None) * REP_SCALE, 0, 255).astype(np.uint8)
        out[:, :, 2] = np.clip(np.clip(-d, 0, None) * REP_SCALE, 0, 255).astype(np.uint8)
        return out
    # flow: Farneback at half resolution, then back up. Half resolution because
    # the dots are ~100 px across and their motion is a few px -- resolving that
    # does not need every pixel, and full resolution costs 4x for nothing.
    h, w = r.shape
    rs = cv2.resize(r, (w // 2, h // 2)).astype(np.uint8)
    gs = cv2.resize(g, (w // 2, h // 2)).astype(np.uint8)
    fl = cv2.calcOpticalFlowFarneback(rs, gs, None, 0.5, 3, 21, 3, 5, 1.2, 0)
    fl = cv2.resize(fl, (w, h)) * 2.0          # px at full resolution
    out = np.zeros(r.shape + (3,), np.uint8)
    out[:, :, 0] = np.clip(128.0 + fl[:, :, 0] * 12.0, 0, 255).astype(np.uint8)
    out[:, :, 1] = np.clip(128.0 + fl[:, :, 1] * 12.0, 0, 255).astype(np.uint8)
    out[:, :, 2] = np.clip(np.abs(g - r) * REP_SCALE, 0, 255).astype(np.uint8)
    return out


def representation(ref_gray, img_gray, norm="none"):
    """9DTact's `raw_image_2_representation`, channel for channel.

    `norm` is an ABLATION, not an improvement. The normal-force task as
    collected is solvable from a single global number -- the mean darkening --
    and area-average downsampling preserves a mean EXACTLY (it is a linear
    operator). Measured 2026-09-08 on 9DTact_medium_2mm_r2: the dark-channel
    mean moves 2.5 % between 1920x1080 and 8x5 (that much only because the
    representation is uint8), and its correlation with Fz goes 0.975 -> 0.968.
    So the information the network mostly uses is very nearly invariant to the
    thing this sweep varies, and no amount of shrinking the model or adding
    noise changes that -- it lowers every cell together and buries the
    comparison rather than exposing it.

      "dc"   subtract each frame's own mean from the difference channels.
             The DC term -- the integral that survives averaging -- is gone;
             the spatial pattern and its amplitude remain.
      "unit" subtract the mean AND divide by the frame's own scale. Now
             absolute amplitude carries nothing either, and the force can only
             be read from the imprint's SHAPE and EXTENT in pixels -- which is
             exactly what resolution destroys, and whose size is set by the
             gel's thickness.

    Signed values are centred on 128 so a uint8 can carry both signs.
    """
    if ref_gray.ndim == 3:
        # COLOUR representation, for DIGIT. A DIGIT imprint is a colour change
        # -- its three LEDs make the channels move in opposite directions --
        # and averaging to grey cancels it (measured 2026-09-08: the dark
        # channel of a grey difference is a fraction of the per-channel
        # movement). The 9DTact recipe above is kept for cross-principle
        # comparability; this is the input that gives a DIGIT a fair reading.
        # Signed per-channel difference, x3 like the 9DTact channels, centred
        # on 128. The reference itself is dropped -- it is constant.
        d = (img_gray.astype(np.float32) - ref_gray.astype(np.float32)) * REP_SCALE
        return np.clip(128.0 + d, 0, 255).astype(np.uint8)
    r = ref_gray.astype(np.float32)
    g = img_gray.astype(np.float32)
    darker = np.clip(r - g, 0, None)
    brighter = np.clip(g - r, 0, None)
    out = np.zeros(ref_gray.shape + (3,), dtype=np.uint8)
    out[:, :, 0] = ref_gray
    if norm == "none":
        out[:, :, 1] = np.clip(brighter * REP_SCALE, 0, 255).astype(np.uint8)
        out[:, :, 2] = np.clip(darker * REP_SCALE, 0, 255).astype(np.uint8)
        return out
    d = darker - darker.mean()
    b = brighter - brighter.mean()
    if norm == "unit":
        s = float(np.sqrt(d.var() + b.var())) + 1e-6
        d = d / s
        b = b / s
        gain = 40.0
    else:
        gain = float(REP_SCALE)
    out[:, :, 1] = np.clip(128.0 + b * gain, 0, 255).astype(np.uint8)
    out[:, :, 2] = np.clip(128.0 + d * gain, 0, 255).astype(np.uint8)
    return out


def load_unit(run: Path, max_frames: int | None = None, norm: str = "none",
              rep: str = "grey", fz_max: float | None = None):
    """Full-resolution 3-channel representations and their 6D wrench labels.

    `rep`: 'grey' is the 9DTact recipe; 'colour' keeps the three camera
    channels (see representation). `fz_max`: drop frames whose |Fz| exceeds
    it -- the collect's fixed range is 0-2 N but the ramp overshoots, by
    0.4-3 % of frames on most units and 14-26 % on the two DIGIT_Marker units
    collected before the step-floor fix (CANONICAL.yaml), so a common cap
    makes the units comparable.
    """
    rows = list(csv.DictReader(open(run / "stream" / "frames.csv")))
    if max_frames:
        rows = rows[:max_frames]
    if fz_max is not None:
        rows = [r for r in rows
                if abs(float(r.get("Fz_s_corr") or r["Fz_s"])) <= fz_max]
    # reference_collect.png -- the median of this run's own lowest-force
    # collect frames -- when present. On every DIGIT run (2026-09-08/09,
    # Pass A and B, 44 of 44) reference.png is 8-14 % BRIGHTER than every
    # frame after it, multiplicatively: the first open of the run grabbed it
    # after two discarded frames, before the sensor had settled to the manual
    # exposure. 9DTact runs show no such gap. Against that reference the
    # 'darker' channel carries a pedestal over the whole field and the
    # imprint rides on top of it. The collect frames at ~0 N are the same
    # gel, same session, same exposure as every other frame.
    # Preference: reference_collect.png (this run's own ~0 N collect frames)
    # > reference_working.png (0 N with the probe at working height, saved at
    # touchcheck from 2026-09-09 on) > reference.png (probe far away -- on a
    # DIGIT that frame is 8-14 % brighter than anything the probe's shadow
    # later allows; see campaign_protocol.md 4.7 (10)).
    for name in ("reference_collect.png", "reference_working.png", "reference.png"):
        if (run / name).exists():
            ref_bgr = cv2.imread(str(run / name)); break
    marker_mode = rep if rep in ("inpaint", "flow") else None
    raw_mode = rep == "raw"
    mask = dot_mask(ref_bgr) if marker_mode == "inpaint" else None
    if marker_mode:
        ref = ref_bgr
    else:
        ref = ref_bgr if rep == "colour" else cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    h, w = ref.shape[:2]
    X = np.zeros((len(rows), h, w, 3), dtype=np.uint8)
    y = np.zeros((len(rows), 6), dtype=np.float32)
    keep = np.ones(len(rows), dtype=bool)
    cyc = np.zeros(len(rows), dtype=np.int32)
    blk = np.zeros(len(rows), dtype=np.int32)      # 0 normal, 1 shear
    for i, r in enumerate(rows):
        img = cv2.imread(str(run / "stream" / r["file"]),
                         cv2.IMREAD_COLOR if rep in ("colour", "inpaint", "flow", "raw")
                         else cv2.IMREAD_GRAYSCALE)
        if img is None or r.get("missing") == "True":
            keep[i] = False
            continue
        if raw_mode:
            # PyTouch's DIGIT recipe feeds the RAW frame -- no reference
            # subtraction at all -- and normalises it like an ImageNet photo.
            # cv2 reads BGR; torchvision's pretrained weights expect RGB.
            X[i] = img[:, :, ::-1]
        elif marker_mode:
            X[i] = marker_representation(ref, img, mask, marker_mode)
        else:
            X[i] = representation(ref, img, norm if norm != "anti" else "none")
        # drift-corrected labels where present, raw otherwise
        y[i] = [float(r.get(f"{ax}_s_corr") or r[f"{ax}_s"]) for ax in AXES]
        y[i, 2] = -y[i, 2]                          # +Fz = pressing
        cyc[i] = int(r["cycle"] or 0)
        blk[i] = 1 if r["segment"].startswith("shear") else 0
    if norm == "anti":
        # ANTISYMMETRIC ablation for shear. Every frame gets the normal-block
        # frame at the nearest Fz subtracted, so whatever the normal load does
        # to the picture -- the monopole that carries most of the pixel energy
        # -- is gone, and what remains is the change the SHEAR made: the dipole
        # (front edge pressed, back edge released) plus sensor noise. For a
        # normal-block frame the nearest other normal frame is subtracted and
        # the result is noise, which is correct: there is no shear to see.
        # This makes Fz unpredictable by construction; it is a shear-only
        # ablation, and fz_mae under it is meaningless. Frames are matched
        # within the whole unit (inputs, not labels -- no label leaks), and
        # the signed difference is centred on 128 in the two difference
        # channels; channel 0 keeps the reference as before.
        X = X[keep]; y = y[keep]; cyc = cyc[keep]; blk = blk[keep]
        fz = y[:, 2]
        lat = np.hypot(y[:, 0], y[:, 1])
        nidx = np.where(blk == 0)[0]
        Xa = np.zeros_like(X)
        Xa[:, :, :, 0] = X[:, :, :, 0]
        for i in range(len(X)):
            if blk[i] == 1:
                # Reference = the LEAST-sheared frame of this same shear cycle.
                # Not a normal-block frame at the same Fz: the shear block
                # comes after the normal block, the gel has crept, and the
                # matched-Fz picture differs by a DC offset that swamped the
                # dipole (measured 2026-09-08 on 9DTact_hard_2mm_r1: shear
                # frames' pixel sign fractions +0.02/-0.11 at EVERY shear level,
                # energy below the noise baseline). Same cycle = same hold,
                # same creep state, minutes apart at most.
                cand = np.where((blk == 1) & (cyc == cyc[i]))[0]
                cand = cand[cand != i]
                if len(cand) == 0:
                    cand = nidx
                j = cand[np.argmin(lat[cand])]
            else:
                cand = nidx[nidx != i]
                j = cand[np.argmin(np.abs(fz[cand] - fz[i]))]
            for ch in (1, 2):
                dlt = X[i, :, :, ch].astype(np.float32) - X[j, :, :, ch].astype(np.float32)
                dlt -= dlt.mean()          # no DC: only the spatial pattern is kept
                Xa[i, :, :, ch] = np.clip(128.0 + dlt, 0, 255).astype(np.uint8)
        return Xa, y, cyc, blk
    return X[keep], y[keep], cyc[keep], blk[keep]


TRAIN_FRAC, VAL_FRAC = 0.70, 0.15      # test takes the remaining 0.15


def split_by_cycle(cyc, blk, train_frac=TRAIN_FRAC, val_frac=VAL_FRAC):
    """Whole cycles, in the order they were pressed: train, then val, then test.

    A frame's neighbours inside one ramp are nearly the same picture at nearly
    the same force, so a random frame split puts near-duplicates on both sides
    and scores a generalisation the model never had to do. Splitting by cycle
    is the honest version, and the harder one: the test cycles are the LAST
    ones pressed, after the gel has been loaded a few hundred times.

    The boundary is placed on the cumulative FRAME count, not on the cycle
    index. Cycles are not equal: a run stops when its frame budget is spent, so
    the last cycle of a block holds 5 to 55 frames where the first holds 78 to
    130. Cutting at cycle 0.85 x n therefore gave 90/8/2 on
    9DTact_soft_2mm_r1 instead of 70/15/15. Val and test still get at least one
    whole cycle each. `split_random` is then told to reproduce whatever
    proportions this reached, so the two definitions differ in HOW they cut and
    not in how much.
    """
    n = len(cyc)
    tr = np.zeros(n, bool); va = np.zeros(n, bool); te = np.zeros(n, bool)
    for b in np.unique(blk):
        m = blk == b
        cs, counts = np.unique(cyc[m], return_counts=True)
        if len(cs) < 3:
            tr |= m
            continue
        frac = np.cumsum(counts) / counts.sum()
        # Boundary = the cycle edge whose achieved fraction is NEAREST the
        # target. The previous rule, searchsorted(frac, target) + 1, put the
        # cycle that crosses the target on the near side, so test got only
        # what was left after it -- and in the shear block, whose cycles are
        # ~50 frames with a short one last, that was the short one:
        # n_test_shear = 12 of 500 on 9DTact_hard_1mm_r1 (2.4 %, target 15 %),
        # and the shear MAE swung 0.020 -> 0.040 between seeds on it. Measured
        # 2026-09-08. Whole cycles still; val and test still get >= 1 each.
        # ... and chosen JOINTLY, with test >= 10 % as a constraint whenever
        # any pair of edges can meet it. Choosing i1 first and i2 after it
        # left 9DTact_hard_1mm_r1's shear block -- five cycles of 130/127/124/
        # 107/12 frames -- with i1 = 3 (76 %) and nothing for i2 but the last
        # cycle: 12 test frames again. With five cycles the nearest whole-
        # cycle split is 51/25/24, and that is the honest one; a 2 % test set
        # is not a split, it is a rounding error.
        nc = len(cs)
        te_frac = 1.0 - train_frac - val_frac
        best, best_ok, best_dev = None, False, 9.9
        for a1 in range(1, nc - 1):
            for a2 in range(a1 + 1, nc):
                ftr = frac[a1 - 1]; fva = frac[a2 - 1] - ftr; fte = 1.0 - frac[a2 - 1]
                # 8 %, not 10 %: with five ~100-frame normal cycles the only
                # splits clearing 10 % test are ~47/23/30, which costs a third
                # of the training data to gain 100 test frames nobody needed
                # (hard_1mm_r2, hard_2mm_r1/r2). 8 % keeps 70/22/8 there --
                # 40 test frames -- and still rejects the 2 % shear case.
                ok = fte >= 0.08
                dev = abs(ftr - train_frac) + abs(fva - val_frac) + abs(fte - te_frac)
                if (ok, -dev) > (best_ok, -best_dev):
                    best, best_ok, best_dev = (a1, a2), ok, dev
        i1, i2 = best
        tr |= m & (cyc < cs[i1])
        va |= m & (cyc >= cs[i1]) & (cyc < cs[i2])
        te |= m & (cyc >= cs[i2])
    return tr, va, te


def split_random(cyc, blk, seed=0, like=None):
    """Frames drawn at random, in the same proportions the cycle split reached.

    Kept alongside the cycle split because the operator asked for both, and
    because the gap between the two IS a measurement: it says how much of the
    apparent accuracy comes from neighbouring frames of one ramp sitting on
    both sides of the split. For that comparison to mean anything the two must
    differ only in the cut, so the sizes are copied from `like` -- the cycle
    split's own (train, val, test) masks.
    """
    n = len(cyc)
    if like is None:
        i1, i2 = int(round(n * TRAIN_FRAC)), int(round(n * (TRAIN_FRAC + VAL_FRAC)))
    else:
        i1 = int(like[0].sum())
        i2 = i1 + int(like[1].sum())
    o = np.random.default_rng(1000 + seed).permutation(n)
    tr = np.zeros(n, bool); va = np.zeros(n, bool); te = np.zeros(n, bool)
    tr[o[:i1]] = True; va[o[i1:i2]] = True; te[o[i2:]] = True
    return tr, va, te


def shrink(X, size):
    w, h = size
    if X.shape[2] == w and X.shape[1] == h:
        return X
    out = np.zeros((len(X), h, w, 3), dtype=np.uint8)
    for i in range(len(X)):
        out[i] = cv2.resize(X[i], (w, h), interpolation=cv2.INTER_AREA)
    return out


# ----------------------------------------------------------------- model --
def resnet18_6():
    """9DTact's model: torchvision ResNet-18, pretrained, fc -> 6."""
    from torchvision import models
    import torch.nn as nn
    try:
        m = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    except Exception:                      # older torchvision
        m = models.resnet18(pretrained=True)
    m.fc = nn.Linear(m.fc.in_features, 6)
    return m


def micro_batch_for(size, base=64):
    """How many images fit on the card at once. NOT the optimiser's batch.

    The batch used to shrink with the picture -- 64 at 426x240, 4 at 1920x1080
    -- so every cell of the resolution table was trained by a different
    optimiser, and 1920x1080 (the cell with the widest seed spread) was the one
    trained with the smallest batch. Gradient accumulation separates the two:
    this is the micro-batch, chosen to fit memory, and `--batch` is the
    effective batch, which is now the same at every resolution.
    """
    px = size[0] * size[1]
    ref = 460 * 345
    return int(max(2, min(base, base * ref / max(px, 1))))


def _to_input(xb, mode):
    """uint8 NCHW on the device -> the float tensor the network sees.

    'raw' is the historical behaviour: 0-255 floats, as 9DTact's dataset does.
    'imagenet' is what PyTouch's DigitSensor does -- ToTensor (which divides by
    255) then Normalize with the ImageNet statistics the pretrained ResNet-18
    weights were fitted under.
    """
    import torch
    x = xb.float()
    if mode != "imagenet":
        return x
    m = torch.tensor(IMAGENET_MEAN, device=x.device).view(1, 3, 1, 1)
    s = torch.tensor(IMAGENET_STD, device=x.device).view(1, 3, 1, 1)
    return (x / 255.0 - m) / s


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def train_eval(X, y, tr, va, te, epochs=30, batch=64, seed=0, device="cuda",
               size=(460, 345), wd=1e-4, patience=0, blk_te=None,
               input_norm="raw"):
    """Train on `tr`, choose the epoch on `va`, report on `te`.

    Three departures from the 2026-09-08 first pass, all asked for after that
    pass turned out to be noise-limited:

    * **One batch for every resolution.** `batch` is the optimiser's batch and
      is the same everywhere; the card sees `micro_batch_for(size)` images at a
      time and the gradients are accumulated. With an L1 loss reduced by SUM
      this is exactly one large step, not an approximation.
    * **A validation split, and the epoch is chosen on it.** Before, every fit
      ran a fixed 30 epochs and whatever it had at the end was reported, so a
      run that had already begun to overfit was scored after it did. The
      weights from the best validation epoch are restored before the test set
      is touched.
    * **Weight decay.** `patience` can also stop training early, but it is OFF
      by default: measured on 2026-09-08, a patience of 8 cut 320x180 off at
      epoch 14 of 30 with train 0.264 against val 0.276 -- the two still
      together, so the run was UNDER-trained, not over -- and the error came
      out 0.079 N where the same cell had reached 0.050 N when allowed to
      finish. Early termination saves time; it is choosing the epoch that
      guards against overfitting, and that costs nothing extra.

    The test set is touched exactly once, at the end.
    """
    import torch
    import torch.nn as nn
    torch.manual_seed(seed)
    np.random.seed(seed)
    net = resnet18_6().to(device)
    micro = min(micro_batch_for(size), batch)
    accum = max(1, int(round(batch / micro)))
    lo, hi = y[tr].min(0), y[tr].max(0)
    rng = np.where(hi - lo < 1e-6, 1.0, hi - lo)

    def prep(m):
        # uint8 on the CPU; the float cast happens per batch on the device.
        # Holding a split as float32 at full resolution is
        # 1000 x 1080 x 1920 x 3 x 4 B = 25 GB, and with the grey and colour
        # sweeps both at 1920x1080 that OOM-killed the machine twice on
        # 2026-09-09 -- systemd then failed the whole app-code scope, which
        # took the editor down with it. The cast is numerically identical
        # (raw 0-255 levels, no scaling), so resumed CSV rows stay comparable.
        return torch.from_numpy(X[m]).permute(0, 3, 1, 2)

    Xtr, Xva, Xte = prep(tr), prep(va), prep(te)
    ytr = torch.from_numpy((y[tr] - lo) / rng).float()
    yva = torch.from_numpy((y[va] - lo) / rng).float()
    opt = torch.optim.Adam(net.parameters(), lr=5e-4, betas=(0.9, 0.999),
                           weight_decay=wd)
    sch = torch.optim.lr_scheduler.LinearLR(opt, start_factor=1.0,
                                            end_factor=0.1, total_iters=epochs)
    lossf = nn.L1Loss(reduction="sum")
    n = len(Xtr)

    def evaluate(Xs, ys=None):
        net.eval()
        out, loss = [], 0.0
        with torch.no_grad():
            for i in range(0, len(Xs), max(2, micro)):
                xb = _to_input(Xs[i:i + max(2, micro)].to(device), input_norm)
                pb = net(xb).float()
                if ys is not None:
                    loss += float(lossf(pb, ys[i:i + max(2, micro)].to(device)))
                out.append(pb.cpu().numpy())
        return np.concatenate(out), (loss / max(len(Xs), 1))

    best = (float("inf"), -1, None)
    hist = []
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(n)
        opt.zero_grad(set_to_none=True)
        tot, k = 0.0, 0
        for i in range(0, n, micro):
            idx = perm[i:i + micro]
            xb = _to_input(Xtr[idx].to(device, non_blocking=True), input_norm)
            yb = ytr[idx].to(device, non_blocking=True)
            loss = lossf(net(xb), yb)
            loss.backward()
            tot += float(loss); k += 1
            if k % accum == 0 or i + micro >= n:
                opt.step()
                opt.zero_grad(set_to_none=True)
        sch.step()
        _, vl = evaluate(Xva, yva)
        hist.append((tot / max(n, 1), vl))
        if vl < best[0] - 1e-9:
            best = (vl, ep, {kk: v.detach().cpu().clone()
                             for kk, v in net.state_dict().items()})
        elif patience and ep - best[1] >= patience:
            break
    if best[2] is not None:
        net.load_state_dict(best[2])

    p_norm, _ = evaluate(Xte)
    p = p_norm * rng + lo
    tt = y[te]
    mae6 = np.abs(p - tt).mean(0)
    lat_p = np.hypot(p[:, 0], p[:, 1])
    lat_t = np.hypot(tt[:, 0], tt[:, 1])
    # Block-separated errors. The test set holds the last cycles of BOTH
    # blocks, and in the normal block the shear label is friction noise
    # (0-0.05 N) that any model predicts as ~0. Averaging those in with the
    # shear-block frames halved the reported shear error and, worse, diluted
    # its resolution dependence with a term that has none. `lat_mae` is kept
    # for continuity; `lat_mae_shear` is the number that means "shear
    # estimation error", and `fz_mae_normal` its counterpart.
    bte = blk_te if blk_te is not None else np.zeros(len(tt), int)
    ms, mn = bte == 1, bte == 0
    lat_mae_shear = float(np.abs(lat_p[ms] - lat_t[ms]).mean()) if ms.any() else np.nan
    fz_mae_normal = float(np.abs(p[mn, 2] - tt[mn, 2]).mean()) if mn.any() else np.nan
    ss = float(1 - np.sum((p[:, 2] - tt[:, 2]) ** 2)
               / max(np.sum((tt[:, 2] - tt[:, 2].mean()) ** 2), 1e-9))
    lat_r2 = float(1 - np.sum((lat_p - lat_t) ** 2)
                   / max(np.sum((lat_t - lat_t.mean()) ** 2), 1e-9))
    tr_loss, va_loss = hist[best[1]] if best[1] >= 0 else (np.nan, np.nan)
    return dict(fz_mae=float(mae6[2]), lat_mae=float(np.abs(lat_p - lat_t).mean()),
                lat_mae_shear=lat_mae_shear, fz_mae_normal=fz_mae_normal,
                n_test_shear=int(ms.sum()), n_test_normal=int(mn.sum()),
                fz_rmse=float(np.sqrt(((p[:, 2] - tt[:, 2]) ** 2).mean())),
                fz_mae_baseline=float(np.abs(tt[:, 2] - y[tr][:, 2].mean()).mean()),
                lat_mae_baseline=float(np.abs(lat_t - np.hypot(y[tr][:, 0],
                                                              y[tr][:, 1]).mean()).mean()),
                fz_r2=ss, lat_r2=lat_r2, batch=batch, micro_batch=micro,
                accum=accum, best_epoch=best[1] + 1, epochs_run=len(hist),
                train_loss=float(tr_loss), val_loss=float(va_loss),
                tx_mae=float(mae6[3]), ty_mae=float(mae6[4]), tz_mae=float(mae6[5]),
                n_train=int(tr.sum()), n_val=int(va.sum()), n_test=int(te.sum()),
                fz_range=float(tt[:, 2].max() - tt[:, 2].min()))


# ------------------------------------------------------------------ main --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units", nargs="*")
    ap.add_argument("--sizes", default=None, help="e.g. 1920x1080,320x180")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--max-frames", type=int, default=None)
    # One seed per (unit, size) makes a table whose cells cannot be compared:
    # measured 2026-09-08, a single unit's error wandered 0.022-0.096 N across
    # the twelve sizes with no order to it, which is what training noise looks
    # like, not resolution. --seeds repeats the fit so the noise can be
    # measured instead of argued about.
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--batch", type=int, default=64,
                    help="the OPTIMISER's batch, the same at every resolution; "
                         "the card sees micro_batch_for(size) at a time and the "
                         "gradients are accumulated")
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--patience", type=int, default=0,
                    help="stop early after this many epochs without a val "
                         "improvement; 0 runs every epoch and keeps the best")
    ap.add_argument("--splits", default="cycle,random",
                    help="which held-out definitions to run")
    ap.add_argument("--norm", choices=["none", "dc", "unit", "anti"], default="none",
                    help="ablation on the input representation. 'none' is the "
                         "9DTact original; 'dc' removes each frame's own mean "
                         "from the difference channels; 'unit' removes the mean "
                         "AND the amplitude, leaving only the imprint's shape "
                         "and extent. See representation().")
    ap.add_argument("--dataset-dir", default=None,
                    help="Pass B dataset folder; default data/9DTact/20260907_passB_ball8. "
                         "The principle prefix is taken from its parent folder name.")
    ap.add_argument("--canonical", default=None,
                    help="CANONICAL.yaml naming one run per unit (skips __N re-runs)")
    ap.add_argument("--rep", choices=["grey", "colour", "inpaint", "flow", "raw"],
                    default="grey",
                    help="input representation. 'grey' = 9DTact recipe (comparable "
                         "across principles); 'colour' = signed per-channel difference, "
                         "the fair input for a DIGIT; 'inpaint' = the marker dots "
                         "masked out of the difference and filled from their "
                         "surroundings, which removes the occlusion the literature "
                         "names as the cost of markers; 'flow' = dense optical flow "
                         "from the reference, which is the Marker Displacement "
                         "Method in a form a CNN can take (see marker_representation); "
                         "'raw' = the frame itself, RGB, no reference subtraction, "
                         "which is what PyTouch's DigitSensor feeds (pair it with "
                         "--input-norm imagenet for DIGIT's own recipe)")
    ap.add_argument("--input-norm", choices=["raw", "imagenet"], default="raw",
                    help="what the network's input scale is. 'raw' keeps 0-255 "
                         "levels, as 9DTact's dtact_dataset.py does and as every "
                         "sweep before 2026-09-10 did. 'imagenet' divides by 255 "
                         "and applies the ImageNet mean/std, which is what "
                         "PyTouch's DigitSensor does (ToTensor + Normalize) and "
                         "what the pretrained ResNet-18 weights were trained for.")
    ap.add_argument("--fz-max", type=float, default=None,
                    help="drop frames with |Fz| above this (N); 2.0 = the fixed range")
    ap.add_argument("--out", default=str(ROOT / "data" / "9DTact" / "force_vs_resolution_v2.csv"))
    a = ap.parse_args()
    sizes = SIZES if not a.sizes else [tuple(int(v) for v in s.split("x"))
                                       for s in a.sizes.split(",")]
    splits = [s.strip() for s in a.splits.split(",") if s.strip()]
    dataset = Path(a.dataset_dir) if a.dataset_dir else DATASET
    prefix = dataset.parent.name + "_"           # 9DTact_ / DIGIT_ / DIGIT_Marker_
    if a.canonical:
        # one run per unit, named by the manifest (re-runs exist as __N)
        import yaml
        man = yaml.safe_load(open(a.canonical))["canonical"]
        runs = [dataset / v["run"] for k, v in man.items()
                if not a.units or k in a.units or k.replace(prefix, "") in a.units]
    else:
        runs = sorted(dataset.glob(prefix + "*")) if not a.units else \
            [dataset / u for u in a.units]
    runs = [r for r in runs if (r / "stream" / "frames.csv").exists()]
    print(f"{len(runs)} units x {len(sizes)} sizes x {len(splits)} splits x "
          f"{a.seeds} seed(s), {a.epochs} epochs, batch {a.batch}")
    out = Path(a.out)
    rows = []
    if out.exists():
        rows = list(csv.DictReader(open(out)))
        print(f"  resuming: {len(rows)} rows already in {out.name}")
    done = {(r["sensor"], int(r["width_px"]), int(r.get("seed") or 0),
             r.get("split") or "cycle") for r in rows}
    cols = ["sensor", "width_px", "height_px", "split", "seed", "fz_mae", "fz_rmse",
            "fz_mae_baseline", "fz_r2", "lat_mae", "lat_mae_baseline", "lat_r2",
            "lat_mae_shear", "fz_mae_normal", "n_test_shear", "n_test_normal", "norm", "rep",
            "n_train", "n_val", "n_test", "fz_range", "tx_mae", "ty_mae", "tz_mae",
            "epochs", "epochs_run", "best_epoch", "train_loss", "val_loss",
            "batch", "micro_batch", "accum", "seconds"]
    for run in runs:
        import re as _re
        sensor = _re.sub(r"__\d+$", "", run.name.replace(prefix, ""))
        todo = [(s, k, sp) for s in sizes for k in range(a.seeds) for sp in splits
                if (sensor, s[0], k, sp) not in done]
        if not todo:
            continue
        t0 = time.time()
        X, y, cyc, blk = load_unit(run, a.max_frames, a.norm, a.rep, a.fz_max)
        print(f"\n{sensor}: {len(X)} frames, Fz {y[:,2].min():+.2f}..{y[:,2].max():+.2f} N, "
              f"decoded in {time.time()-t0:.0f}s", flush=True)
        last_size, Xs = None, None
        for size, seed, sp in sorted(todo, key=lambda z: (-z[0][0], z[2], z[1])):
            t1 = time.time()
            if size != last_size:
                Xs, last_size = shrink(X, size), size
            cut = split_by_cycle(cyc, blk)
            tr, va, te = cut if sp == "cycle" else split_random(cyc, blk, seed, like=cut)
            r = train_eval(Xs, y, tr, va, te, epochs=a.epochs, batch=a.batch,
                           input_norm=a.input_norm,
                           seed=seed, size=size, wd=a.weight_decay,
                           patience=a.patience, blk_te=blk[te])
            r.update(sensor=sensor, width_px=size[0], height_px=size[1], seed=seed,
                     split=sp, epochs=a.epochs, seconds=round(time.time() - t1, 1),
                     norm=a.norm, rep=a.rep, input_norm=a.input_norm)
            rows.append(r)
            print(f"  {size[0]:5d}x{size[1]:<4d} {sp:6} s{seed} "
                  f"Fz MAE {r['fz_mae']:.4f} R2 {r['fz_r2']:+.3f}  "
                  f"lat {r['lat_mae']:.4f} R2 {r['lat_r2']:+.3f}  "
                  f"ep {r['best_epoch']}/{r['epochs_run']}  "
                  f"tr {r['train_loss']:.3f} va {r['val_loss']:.3f}  "
                  f"{r['seconds']:.0f}s", flush=True)
            with open(out, "w", newline="") as fh:
                wtr = csv.DictWriter(fh, fieldnames=cols)
                wtr.writeheader()
                for rr in rows:
                    rr.setdefault("seed", 0)
                    rr.setdefault("split", "cycle")
                    wtr.writerow({c: rr.get(c) for c in cols})
        del X
    print(f"\n-> {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
